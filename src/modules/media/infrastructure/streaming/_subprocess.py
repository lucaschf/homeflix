"""Shared subprocess kwargs for ffprobe/ffmpeg calls.

Centralises the encoding and output-capture settings so that every
subprocess.run() call in the streaming package stays consistent.
"""

from types import MappingProxyType
from typing import Any

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
    if max_threads is None or not cmd or cmd[0] != "ffmpeg":
        return cmd
    return [cmd[0], "-threads", str(max_threads), *cmd[1:]]
