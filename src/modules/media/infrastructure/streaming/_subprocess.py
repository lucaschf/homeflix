"""Shared subprocess kwargs for ffprobe/ffmpeg calls.

Centralises the encoding and output-capture settings so that every
subprocess.run() call in the streaming package stays consistent.
"""

from typing import Any

#: Common kwargs for ``subprocess.run`` calls that capture text output.
#: Each call site should unpack this and add its own ``timeout``.
SUBPROCESS_TEXT_KWARGS: dict[str, Any] = {
    "capture_output": True,
    "text": True,
    "encoding": "utf-8",
    "errors": "replace",
}
