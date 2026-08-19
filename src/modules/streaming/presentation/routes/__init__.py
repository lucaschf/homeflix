"""Streaming API routes."""

from src.modules.streaming.presentation.routes.admin_now_playing_routes import (
    router as admin_now_playing_router,
)
from src.modules.streaming.presentation.routes.admin_subtitle_ocr_routes import (
    router as admin_subtitle_ocr_router,
)
from src.modules.streaming.presentation.routes.admin_system_routes import (
    router as admin_system_router,
)
from src.modules.streaming.presentation.routes.direct_stream_routes import (
    router as direct_stream_router,
)
from src.modules.streaming.presentation.routes.hls_routes import router as hls_router

__all__ = [
    "admin_now_playing_router",
    "admin_subtitle_ocr_router",
    "admin_system_router",
    "direct_stream_router",
    "hls_router",
]
