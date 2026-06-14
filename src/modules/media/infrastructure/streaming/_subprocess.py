"""Shared subprocess kwargs for ffprobe/ffmpeg calls.

Centralises the encoding and output-capture settings so that every
subprocess.run() call in the streaming package stays consistent.
"""

from types import MappingProxyType
from typing import Any

# HardwareAccel.* string values, compared by value (HardwareAccel is a
# StrEnum) so the streaming infrastructure stays decoupled from the
# settings domain — media imports settings only under TYPE_CHECKING
# (ADR-008). Kept here, beside the other shared ffmpeg helpers, so the
# HLS and thumbnail services read one source of truth instead of each
# carrying its own copy.
HW_ACCEL_OFF = "off"
HW_ACCEL_NVENC = "nvenc"

# Match against the binary's basename so absolute paths
# (``/usr/bin/ffmpeg``) and the Windows executable suffix
# (``ffmpeg.exe``) both flow through the cap. A bare ``cmd[0] ==
# "ffmpeg"`` check would silently no-op on either, leaving the
# threads cap unapplied without any signal.
_FFMPEG_BINARY_NAMES = frozenset({"ffmpeg", "ffmpeg.exe"})


def _binary_name(argv0: str) -> str:
    """Return the lowercase binary filename from an ``argv[0]`` value.

    Splits on both POSIX and Windows separators so the result is the
    same regardless of the host OS — ``Path.name`` /
    ``os.path.basename`` are platform-aware and would treat a Windows
    path on Linux (or vice versa) as a single filename, defeating the
    purpose of normalising the binary name here.
    """
    return argv0.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()


#: Common kwargs for ``subprocess.run`` calls that capture text output.
#: Each call site should unpack this and add its own ``timeout``.
SUBPROCESS_TEXT_KWARGS: MappingProxyType[str, Any] = MappingProxyType(
    {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
)


def with_ffmpeg_threads(cmd: list[str], max_threads: int | None) -> list[str]:
    """Inject ``-threads N`` right after ``ffmpeg`` to cap parallelism.

    ffmpeg's default thread count is "auto" — it spawns one worker per
    logical core, which on a typical desktop saturates the machine
    during transcoding. Passing ``-threads N`` caps internal worker
    threads to ``N``; in practice this caps CPU usage to roughly
    ``N / total_logical_cores`` since each worker pegs one core.

    Returns ``cmd`` unchanged when ``max_threads`` is ``None`` (no cap
    configured) or when the command isn't an ffmpeg invocation, so
    callers can wrap unconditionally. The flag is inserted at index 1
    rather than appended because ffmpeg treats it as a global option
    and a few ffmpeg versions are picky about its position relative
    to ``-i``.

    Args:
        cmd: Full subprocess argv. Untouched when no cap applies.
        max_threads: Maximum worker thread count, or ``None`` for the
            default auto behaviour.

    Returns:
        Either ``cmd`` itself or a new list with ``-threads N``
        inserted after the binary.
    """
    if max_threads is None or not cmd:
        return cmd
    if _binary_name(cmd[0]) not in _FFMPEG_BINARY_NAMES:
        return cmd
    return [cmd[0], "-threads", str(max_threads), *cmd[1:]]
