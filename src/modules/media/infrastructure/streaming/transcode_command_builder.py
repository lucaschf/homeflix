"""FFmpeg command construction for HLS video and audio tracks.

Extracted from ``HlsService`` (pure: no locks, no threads, no subprocess
*spawning* — it only builds argv lists). The video command consults an
injected :class:`HardwareAccelerationProbe` to pick the NVENC or libx264
pipeline; the audio helpers decide copy-vs-re-encode and probe for a
leading silent gap.
"""

from __future__ import annotations

import logging
import subprocess
from typing import TYPE_CHECKING

from src.modules.media.infrastructure.streaming._hls_common import (
    BROWSER_SAFE_CODECS,
    SEGMENT_DURATION,
    primary_audio_index,
)
from src.modules.media.infrastructure.streaming._subprocess import SUBPROCESS_TEXT_KWARGS

if TYPE_CHECKING:
    from pathlib import Path

    from src.modules.media.application.ports.media_probe_port import ProbeResult
    from src.modules.media.infrastructure.streaming.hardware_acceleration_probe import (
        HardwareAccelerationProbe,
    )
    from src.shared_kernel.value_objects.tracks import AudioTrack

_logger = logging.getLogger(__name__)


# A leading audio offset above this many seconds is treated as a gap that
# must be padded with silence (see ``_first_audio_pts``). The threshold is
# generous — normal muxing jitter is a few milliseconds, so anything past a
# quarter-second is a real hole at the head of the track, not noise.
_AUDIO_LEADING_GAP_THRESHOLD = 0.25


def _first_audio_pts(file_path: str, audio_index: int) -> float | None:
    """Return the PTS (seconds) of the first packet of one audio stream.

    Some source files carry an audio track whose first sample lands well
    after t=0 (e.g. an 11-second silent hole at the head of the stream).
    Muxed into HLS from t=0, the leading segments then declare an audio
    stream that has *no* frames yet, and hls.js — which needs the audio
    codec from the first fragment — stalls forever on that phantom track
    instead of ever appending a buffer. Detecting the offset lets the
    caller pad it with silence and keep the copy fast-path off files that
    would otherwise ship an empty-audio first segment.

    Args:
        file_path: Absolute path to the source video file.
        audio_index: Stream index *within the audio streams* (the ``N`` in
            ffmpeg's ``0:a:N``), matching how the transcode maps it.

    Returns:
        The first packet's presentation timestamp in seconds, or ``None``
        if ffprobe fails or reports no readable timestamp (caller then
        assumes no gap).
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                f"a:{audio_index}",
                "-read_intervals",
                "%+#1",
                "-show_entries",
                "packet=pts_time",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            **SUBPROCESS_TEXT_KWARGS,
            check=False,
            timeout=10,
        )
    except Exception:
        return None
    raw = result.stdout.strip().splitlines()
    if not raw:
        return None
    try:
        return float(raw[0])
    except ValueError:
        return None


def _has_leading_audio_gap(file_path: str, audio_index: int, start: int) -> bool:
    """Whether a mapped audio stream begins meaningfully after t=0.

    Only meaningful for the initial (``start == 0``) bucket — a seek
    bucket lands mid-stream where audio already exists and normalises its
    own timestamps, so we skip the probe there and never treat it as a
    gap. See :func:`_first_audio_pts` for why the gap matters.
    """
    if start != 0:
        return False
    pts = _first_audio_pts(file_path, audio_index)
    return pts is not None and pts > _AUDIO_LEADING_GAP_THRESHOLD


def _audio_args_for(
    track: AudioTrack | None,
    start: int,
    leading_gap: bool = False,
) -> list[str]:
    """Pick the ffmpeg audio args for one HLS track: copy or re-encode.

    Re-encoding every audio track to AAC stereo 48 kHz is wasted work
    when the source already *is* browser-playable AAC. We remux with
    ``-c:a copy`` only when the track is unambiguously safe to drop into
    MPEG-TS untouched:

    - **AAC-LC** — the one AAC profile MSE/hls.js decode everywhere;
      HE-AAC (SBR/PS) is excluded because browser support is spotty.
    - **stereo** — multichannel must be downmixed to 2.0 for the player.
    - **48 kHz** — matches the rate the re-encode path normalises to, so
      a copied stream is byte-for-byte what a transcode would have
      targeted.
    - **start == 0** — a non-zero resume offset re-encodes the video with
      ``-accurate_seek``; copying the audio there would land it at the
      nearest packet instead of the exact second and drift out of sync.
    - **no leading gap** — a track whose first sample lands after t=0
      (``leading_gap``) must be re-encoded so the silence filter below
      can backfill the hole; copying would preserve it and ship an
      empty-audio first segment that stalls hls.js.

    Anything else (unknown profile/rate, non-AAC, surround, mid-stream
    seek, leading gap) falls back to the safe AAC re-encode.

    On the re-encode path for an initial (``start == 0``) bucket we add
    ``aresample=async=1:first_pts=0``. It pads any leading offset with
    silence so the audio starts at t=0 and the first HLS segment carries
    decodable frames — without it, a file whose audio begins late (a real
    silent intro) yields a first segment with a declared-but-empty audio
    stream, and hls.js hangs on "preparing" forever. It is a no-op for a
    track that already starts at zero. The seek path (``start > 0``)
    already normalises timestamps via ``-avoid_negative_ts make_zero`` and
    is left untouched.
    """
    if (
        track is not None
        and start == 0
        and not leading_gap
        and track.codec == "aac"
        and track.is_stereo
        and track.sample_rate == 48000
        and (track.profile or "").strip().upper() == "LC"
    ):
        return ["-c:a", "copy"]
    args = ["-c:a", "aac", "-ac", "2", "-ar", "48000"]
    if start == 0:
        args += ["-af", "aresample=async=1:first_pts=0"]
    return args


class TranscodeCommandBuilder:
    """Build the ffmpeg argv lists for the video and audio HLS tracks.

    Args:
        hw_probe: Resolves whether a transcode runs on NVENC or libx264
            and detects the source video codec.
    """

    def __init__(self, hw_probe: HardwareAccelerationProbe) -> None:
        self._hw_probe = hw_probe

    def build_video_cmd(
        self,
        file_path: str,
        output_dir: Path,
        probe: ProbeResult,
        start: int = 0,
        force_software: bool = False,
        end: int | None = None,
    ) -> list[str]:
        """Build FFmpeg command for video + default audio.

        Transcodes (or remuxes, for already-H.264 sources) from the
        ``start`` second of the file. ``-ss`` is placed BEFORE ``-i``
        so ffmpeg does an input seek — fast and keyframe-accurate —
        and the resulting segments carry timestamps starting near zero
        in bucket-local time. Bucket-local timestamps are why the
        frontend computes ``video.currentTime = saved - bucket_start``
        instead of ``video.currentTime = saved`` (which would only
        work with ``-copyts`` / source-time preserved, a path the
        prior attempts at this refactor never landed reliably).

        When ``start > 0`` we also emit ``-accurate_seek`` and
        ``-avoid_negative_ts make_zero``. The first forces ffmpeg to
        decode-and-drop frames between the preceding keyframe and the
        exact requested second; without it, video opens at the
        keyframe while audio opens at ``start`` and the two streams
        play out of sync by that gap. The second clamps the minimum
        PTS to zero across streams so any residual offset surfaces as
        a tiny silence prefix instead of an audio-leads-video drift.

        The H.264 ``-c:v copy`` fast path is bypassed for non-zero
        ``start`` because copying skips the decode pass that
        ``-accurate_seek`` relies on to drop pre-target frames — the
        copied video would land at the preceding keyframe while the
        re-encoded audio lands at the exact ``start``, recreating the
        same 1-3s gap the seek flag was meant to close.

        When a transcode is required and ``hw_accel`` resolves to NVENC,
        the whole pipeline runs on the GPU: ``-hwaccel cuda`` decodes
        with NVDEC, ``scale_cuda=format=nv12`` does the 10-bit→8-bit
        conversion in VRAM, and ``h264_nvenc`` encodes — keeping the CPU
        almost idle and staying well above real-time on 4K HEVC. The
        software ``libx264`` path is the fallback.
        """
        codec = self._hw_probe.probe_video_codec(file_path)
        needs_transcode = codec not in BROWSER_SAFE_CODECS or start > 0

        hwaccel_input_args: list[str] = []
        vf_args: list[str] = []

        if needs_transcode and self._hw_probe.use_nvenc() and not force_software:
            _logger.info("Source codec %s — transcoding via NVENC (start=%d)", codec, start)
            # Full-GPU pipeline: NVDEC decode → scale_cuda (10→8 bit in
            # VRAM) → NVENC encode. ``spatial_aq`` redistributes bits to
            # flat regions, which is what keeps sky/fog gradients from
            # banding. ``-cq 19`` is constant-quality VBR (``-b:v 0``).
            hwaccel_input_args = ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
            vf_args = ["-vf", "scale_cuda=format=nv12"]
            video_args = [
                "-c:v",
                "h264_nvenc",
                "-preset",
                "p5",
                "-tune",
                "hq",
                "-rc",
                "vbr",
                "-cq",
                "19",
                "-b:v",
                "0",
                "-spatial_aq",
                "1",
            ]
        elif needs_transcode:
            _logger.info("Source codec %s — transcoding via libx264 (start=%d)", codec, start)
            # ``superfast`` (not ``ultrafast``) is the floor here: ultrafast
            # disables CABAC and adaptive quantization, which is exactly what
            # collapses smooth gradients (sky, fog) into visible macroblocks
            # on HEVC/10-bit sources re-encoded to H.264. superfast turns both
            # back on for a moderate CPU cost while staying real-time on 4K.
            # ``-pix_fmt yuv420p`` forces a clean 8-bit output so 10-bit
            # sources (yuv420p10le) downconvert through swscale's dithering
            # instead of producing an unplayable High 10 stream.
            video_args = [
                "-c:v",
                "libx264",
                "-preset",
                "superfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
            ]
        else:
            _logger.info("Source codec %s — copying", codec)
            # H.264 inside MP4/MKV is AVCC (length-prefixed NALs) with
            # SPS/PPS only in container extradata. The HLS muxer does not
            # reliably auto-insert the Annex-B conversion the bare mpegts
            # muxer applies, so sources that don't repeat parameter sets
            # in-band lose them in the .ts segments — the browser decodes
            # zero frames (black video, audio fine). h264_mp4toannexb
            # converts to Annex-B and writes SPS/PPS in-band; it is a
            # no-op for streams already in Annex-B form.
            video_args = ["-c:v", "copy", "-bsf:v", "h264_mp4toannexb"]

        primary_idx = primary_audio_index(probe)
        audio_map = f"0:a:{primary_idx}"
        primary_track = probe.audio_tracks[0] if probe.audio_tracks else None
        leading_gap = _has_leading_audio_gap(file_path, primary_idx, start)
        audio_args = _audio_args_for(primary_track, start, leading_gap)

        seek_args = ["-ss", str(start), "-accurate_seek"] if start > 0 else []
        ts_normalize_args = ["-avoid_negative_ts", "make_zero"] if start > 0 else []
        # Clamp the encode to a sub-range when this title occupies only part
        # of a shared physical file (ADR-030). ``-t`` is an output option, so
        # with the input seek above it measures from ``start``: the emitted
        # stream is exactly ``[start, end)`` source seconds.
        duration_args = ["-t", str(end - start)] if end is not None else []

        return [
            "ffmpeg",
            *hwaccel_input_args,
            *seek_args,
            "-i",
            file_path,
            "-map",
            "0:v:0",
            "-map",
            audio_map,
            "-sn",
            *vf_args,
            *video_args,
            *audio_args,
            *ts_normalize_args,
            *duration_args,
            # Zero the MPEG-TS muxer's ~1.4s initial offset so the first
            # segment PTS starts at ~0, keeping the video / audio / subtitle
            # timelines aligned (the WebVTT X-TIMESTAMP-MAP anchors to MPEGTS:0).
            "-muxdelay",
            "0",
            "-muxpreload",
            "0",
            "-hls_time",
            str(SEGMENT_DURATION),
            "-hls_list_size",
            "0",
            "-hls_playlist_type",
            "event",
            # temp_file: write each segment to .ts.tmp and rename to .ts
            # only after it's fully written. Prevents the player from
            # racing the encoder and grabbing partial bytes.
            "-hls_flags",
            "temp_file",
            "-hls_segment_filename",
            str(output_dir / "segment_%04d.ts"),
            "-loglevel",
            "error",
            "-y",
            str(output_dir / "playlist.m3u8"),
        ]

    @staticmethod
    def build_audio_cmd(
        file_path: str,
        output_dir: Path,
        track: AudioTrack,
        start: int = 0,
        end: int | None = None,
    ) -> list[str]:
        """Build FFmpeg command for audio-only HLS track.

        ``-ss`` placed before ``-i`` when ``start > 0`` — same input-seek
        rationale as ``build_video_cmd``. The alternate-audio playlist
        is consumed independently by the player; even though there is
        no video stream here, we still match the video pipeline's
        ``-accurate_seek`` / ``-avoid_negative_ts make_zero`` so a
        switch from primary to alternate audio at a non-zero bucket
        lands on the same source-time second.

        Like the primary audio in ``build_video_cmd``, a browser-ready
        AAC-LC stereo 48 kHz source is remuxed with ``-c:a copy`` instead
        of re-encoded; see :func:`_audio_args_for`.
        """
        seek_args = ["-ss", str(start), "-accurate_seek"] if start > 0 else []
        ts_normalize_args = ["-avoid_negative_ts", "make_zero"] if start > 0 else []
        # Clamp to the same sub-range as the video track (ADR-030) so an
        # alternate-audio playlist ends at the title boundary, not the file's.
        duration_args = ["-t", str(end - start)] if end is not None else []
        leading_gap = _has_leading_audio_gap(file_path, track.index, start)
        return [
            "ffmpeg",
            *seek_args,
            "-i",
            file_path,
            "-map",
            f"0:a:{track.index}",
            "-vn",
            "-sn",
            *_audio_args_for(track, start, leading_gap),
            *ts_normalize_args,
            *duration_args,
            # Zero the MPEG-TS muxer's ~1.4s initial offset so the first
            # segment PTS starts at ~0, keeping the video / audio / subtitle
            # timelines aligned (the WebVTT X-TIMESTAMP-MAP anchors to MPEGTS:0).
            "-muxdelay",
            "0",
            "-muxpreload",
            "0",
            "-hls_time",
            str(SEGMENT_DURATION),
            "-hls_list_size",
            "0",
            "-hls_playlist_type",
            "event",
            "-hls_flags",
            "temp_file",
            "-hls_segment_filename",
            str(output_dir / "segment_%04d.ts"),
            "-loglevel",
            "error",
            "-y",
            str(output_dir / "playlist.m3u8"),
        ]


__all__ = ["TranscodeCommandBuilder"]
