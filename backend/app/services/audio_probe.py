"""Best-effort audio duration probing without ffmpeg.

WAV is parsed from the RIFF header. For other formats the caller should
supply `duration_seconds` in the form data (the browser MediaRecorder reports
it). Otherwise a conservative file-size heuristic is used so we never
under-count usage.
"""

from typing import Optional


def estimate_wav_duration_seconds(data: bytes) -> Optional[float]:
    if len(data) < 44 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    try:
        idx = 12
        byte_rate = None
        data_size = None
        while idx + 8 <= len(data):
            chunk_id = data[idx:idx + 4]
            chunk_size = int.from_bytes(data[idx + 4:idx + 8], "little")
            if chunk_id == b"fmt " and chunk_size >= 16 and idx + 24 <= len(data):
                byte_rate = int.from_bytes(data[idx + 16:idx + 20], "little")
            elif chunk_id == b"data":
                data_size = chunk_size
                break
            idx += 8 + chunk_size + (chunk_size % 2)
        if byte_rate and data_size and byte_rate > 0:
            return data_size / byte_rate
    except Exception:  # noqa: BLE001 — malformed WAV must not crash the route
        return None
    return None


def estimate_duration_seconds(
    data: bytes,
    content_type: Optional[str],
    fallback_seconds: int,
) -> int:
    if content_type and "wav" in content_type.lower():
        wav = estimate_wav_duration_seconds(data)
        if wav is not None:
            return max(1, int(round(wav)))

    # ~8 kbps conservative lower bound for compressed formats (MP3/OGG/M4A).
    # This intentionally over-charges rather than under-charges.
    by_size = len(data) / 1000.0
    if by_size < 1:
        return 1
    return max(1, min(int(round(by_size)), fallback_seconds))