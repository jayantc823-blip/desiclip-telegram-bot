# DesiClip Telegram Bot

Private Telegram-controlled video clipper with a minimal HTTP health endpoint suitable for Koyeb. Telegram is the control surface; GET `/health` (and `/`) returns `200 OK`.

## Koyeb Free Tier deployment

1. Build this repository as a Docker application (the included `Dockerfile` uses `python:3.11-slim`).
2. Set `TELEGRAM_BOT_TOKEN` and `ALLOWED_CHAT_ID` as Koyeb secrets/environment variables. Optionally add `GEMINI_API_KEY`; do not commit real keys.
3. Set the service's exposed HTTP port to `8000` (or use Koyeb's injected `PORT`) and configure the HTTP health check path as `/health`.
4. Free-tier resources and availability can change. A 512 MB memory instance may restart or be suspended based on the provider's current policies; it cannot guarantee 24/7 uptime.

The container defaults to `WHISPER_MODEL=tiny`, one CPU thread for Whisper/FFmpeg, a bounded queue of four jobs, and a 720p yt-dlp selection. Use `base` only on a host with more memory. Heavy source videos can still cause out-of-memory restarts; keep upload size small. SQLite and assets are ephemeral unless a persistent volume is configured.

## Deploy locally

Python 3.10+ and FFmpeg/ffprobe are required. On Debian/Ubuntu:

```bash
sudo apt-get update && sudo apt-get install -y --no-install-recommends ffmpeg curl fonts-dejavu-core fonts-noto-core
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: TELEGRAM_BOT_TOKEN and ALLOWED_CHAT_ID are required.
python app.py
```

## Features and usage

- Strict allowlist: every command, callback, and media handler checks `ALLOWED_CHAT_ID`.
- `/start` opens an inline menu to add/remove YouTube, Twitch, and Kick watch entries, change TTS voice, save an avatar and BGM, and inspect queue/disk status.
- Send a supported video URL or Telegram video (up to `MAX_VIDEO_MB`, default 20MB) to queue it. Live stream checks run every 60 seconds; live inputs are captured as sequential five-minute chunks.
- CPU Whisper transcription (lazy-loaded, tiny int8 by default), RMS/speech-based segment ranking, optional Gemini or Ollama script generation, and offline Hindi fallback.
- Edge TTS, ASS captions, FFmpeg vertical crop, hook banner, optional avatar overlay and music, and direct Telegram delivery.
- Each rendered clip and voice file is removed after successful delivery; source and intermediate files are removed when the job finishes.

## Configuration

Copy `.env.example` to `.env`. Deployment platforms should configure values as secret environment variables:

- `TELEGRAM_BOT_TOKEN`, `ALLOWED_CHAT_ID` — required.
- `GEMINI_API_KEY`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL` — optional script generation.
- `WHISPER_MODEL=tiny` — low-memory default; `base` improves transcription on larger hosts.
- `PORT=8000` — health server port; the service binds to `0.0.0.0`.

The health server is implemented with Python's standard library and returns immediately without loading a web framework. Gemini, Edge TTS and source-site availability/quotas are external dependencies. If Edge TTS fails, the clip uses its source audio. The avatar is an image overlay, not phoneme-accurate lip sync. The ranking score is only a heuristic, not a guarantee of virality. Only process content you have permission to download, edit, and redistribute.
