"""Audio-energy and optional Whisper analysis, optimized for CPU-only hosts."""
import asyncio
import logging
import subprocess
from pathlib import Path
import numpy as np
import soundfile as sf

log = logging.getLogger(__name__)

async def _run(*args):
    return await asyncio.to_thread(subprocess.run, args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

async def media_duration(path: Path) -> float:
    proc = await asyncio.create_subprocess_exec("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, _ = await proc.communicate()
    try:
        return max(0.0, float(out.decode().strip()))
    except ValueError:
        return 0.0

async def extract_audio(video: Path, wav: Path):
    # Audio-only decode: use a single thread (video encoder preset is not applicable).
    await _run("ffmpeg", "-y", "-threads", "1", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav))

async def _transcribe(wav: Path, model_name: str):
    def work():
        from faster_whisper import WhisperModel
        model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=1, num_workers=1)
        segments, _info = model.transcribe(str(wav), vad_filter=True, word_timestamps=False, beam_size=1)
        return [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()} for s in segments if s.text.strip()]
    try:
        return await asyncio.to_thread(work)
    except Exception as exc:
        log.warning("Whisper unavailable; continuing with energy-only analysis: %s", exc)
        return []

async def analyze(video: Path, workdir: Path, clip_seconds: int, model_name: str):
    wav = workdir / "analysis.wav"
    await extract_audio(video, wav)
    duration = await media_duration(video)
    if duration <= 0:
        return []
    transcript = await _transcribe(wav, model_name)
    data, rate = await asyncio.to_thread(sf.read, wav, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    step = 2.0
    frame = max(1, int(rate * step))
    rms = np.array([np.sqrt(np.mean(data[i:i+frame] ** 2) + 1e-12) for i in range(0, len(data), frame)])
    candidates = []
    length = min(float(clip_seconds), duration)
    starts = list(np.arange(0, max(0.1, duration - length + 0.01), max(5.0, length / 3))) or [0.0]
    for start in starts:
        end = min(duration, start + length)
        lo, hi = int(start / step), max(int(start / step) + 1, int(end / step))
        energy = float(np.mean(rms[lo:hi])) if lo < len(rms) else 0.0
        speech = sum(max(0.0, min(end, s["end"]) - max(start, s["start"])) for s in transcript)
        excerpt = " ".join(s["text"] for s in transcript if s["start"] < end and s["end"] > start)
        # Heuristic ranking only; this is not a prediction of actual virality.
        score = min(99, int(35 + min(35, energy * 150) + min(29, speech / max(1, length) * 35)))
        candidates.append({"start": start, "end": end, "score": score, "transcript": excerpt})
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:2]
