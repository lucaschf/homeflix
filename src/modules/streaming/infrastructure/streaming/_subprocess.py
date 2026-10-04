"""Hardware-acceleration constants shared by the streaming ffmpeg services.

The generic subprocess helpers (text kwargs, ffmpeg thread cap) live in
``src.building_blocks.infrastructure.ffmpeg_subprocess``.
"""

# HardwareAccel.* string values, compared by value (HardwareAccel is a
# StrEnum) so the streaming infrastructure stays decoupled from the
# settings domain — media imports settings only under TYPE_CHECKING
# (ADR-008). Kept in one place so the HLS and thumbnail services read
# one source of truth instead of each carrying its own copy.
HW_ACCEL_OFF = "off"
HW_ACCEL_NVENC = "nvenc"
