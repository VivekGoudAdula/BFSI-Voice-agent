"""Audio utilities for Twilio Media Streams."""

import asyncio
import base64
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any, Iterator

# mulaw @ 8 kHz: 1 byte per sample
MULAW_SAMPLE_RATE = 8000

# 40 ms chunks — fewer WebSocket frames, less JSON overhead than 20 ms
TWILIO_MULAW_CHUNK_SIZE = 320

# Send audio slightly ahead of playback so Twilio's jitter buffer stays full
PLAYBACK_BUFFER_LEAD_SEC = 0.25


def chunk_mulaw_audio(
    audio: bytes, chunk_size: int = TWILIO_MULAW_CHUNK_SIZE
) -> Iterator[bytes]:
    """Split raw mulaw bytes into Twilio-friendly chunks."""
    for offset in range(0, len(audio), chunk_size):
        yield audio[offset : offset + chunk_size]


def encode_mulaw_payload(audio_chunk: bytes) -> str:
    """Base64-encode a mulaw audio chunk for Twilio media messages."""
    return base64.b64encode(audio_chunk).decode("ascii")


def decode_twilio_payload(payload: str) -> bytes:
    """Decode base64 mulaw audio from a Twilio media packet."""
    return base64.b64decode(payload)


def mulaw_duration_sec(num_bytes: int) -> float:
    """Duration of mulaw audio in seconds."""
    return num_bytes / MULAW_SAMPLE_RATE


async def stream_mulaw_to_twilio(
    websocket: Any,
    stream_sid: str,
    audio: bytes,
    is_cancelled: Callable[[], bool],
    on_playback_start: Callable[[], None] | None = None,
    on_playback_end: Callable[[], None] | None = None,
) -> None:
    """
    Stream mulaw audio to Twilio at real-time pace with a small lead buffer.

    Pacing uses wall-clock timing instead of fixed per-chunk sleeps, which
    avoids stutter from event-loop jitter and WebSocket send latency.
    """
    if not audio or not stream_sid:
        return

    playback_start = time.perf_counter()
    bytes_sent = 0
    playback_started = False

    for chunk in chunk_mulaw_audio(audio):
        if is_cancelled():
            break

        # Schedule: send this chunk early enough that Twilio can buffer it
        bytes_sent += len(chunk)
        play_at = playback_start + mulaw_duration_sec(bytes_sent)
        send_at = play_at - PLAYBACK_BUFFER_LEAD_SEC
        delay = send_at - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)

        if is_cancelled():
            break

        if not playback_started:
            playback_started = True
            if on_playback_start:
                on_playback_start()

        payload = encode_mulaw_payload(chunk)
        await websocket.send_text(
            json.dumps(
                {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload},
                },
                separators=(",", ":"),
            )
        )

    # Wait for the last audio to finish playing before returning
    if not is_cancelled() and bytes_sent:
        remaining = mulaw_duration_sec(bytes_sent) - (time.perf_counter() - playback_start)
        if remaining > 0:
            await asyncio.sleep(remaining)

    if not is_cancelled() and on_playback_end:
        on_playback_end()


async def stream_mulaw_chunks_to_twilio(
    websocket: Any,
    stream_sid: str,
    audio_chunks: AsyncIterator[bytes],
    is_cancelled: Callable[[], bool],
) -> None:
    """
    Play Sarvam (or other) mulaw chunks to Twilio as they arrive.

    Time-to-first-audio is much lower than buffering the full utterance first.
    """
    if not stream_sid:
        return

    async for raw_chunk in audio_chunks:
        if is_cancelled():
            break
        for frame in chunk_mulaw_audio(raw_chunk):
            if is_cancelled():
                break
            payload = encode_mulaw_payload(frame)
            await websocket.send_text(
                json.dumps(
                    {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": payload},
                    },
                    separators=(",", ":"),
                )
            )
            await asyncio.sleep(mulaw_duration_sec(len(frame)))
