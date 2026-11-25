# DesiClip Telegram Bot

Private Telegram-controlled video clipper with an optional lightweight Hugging Face Spaces status screen. Telegram is the control surface; the Gradio page is informational only.

## Features

- Strict allowlist: every command, callback, and media handler checks `ALLOWED_CHAT_ID`.
- `/start` inline menu to add/remove YouTube, Twitch, and Kick watch entries, change TTS voice, save an avatar and BGM, and inspect queue/disk status.
- Send a supported video URL or Telegram video to queue it. Live stream checks run every 60 seconds; live inputs are captured as sequential five-minute chunks.
- CPU Whisper transcription (lazy-loaded, `base`, int8), RMS/speech-based segment ranking, optional Gemini or Ollama script generation, and offline Hindi fallback.
- Edge TTS, ASS captions, FFmpeg vertical crop, hook banner, optional avatar overlay and music, and direct Telegram delivery.
- Temporary work and downloaded sources are removed after the job; the SQLite clip counter/watchlist persist under `data/`.

## Deploy locally

Python 3.10+ and FFmpeg/ffprobe are required. On Debian/Ubuntu:

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg fonts-dejavu-core fonts-noto-core
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: TELEGRAM_BOT_TOKEN and ALLOWED_CHAT_ID are required.
python app.py
```

Never commit `.env`. Deployment platforms should configure the same values as secret environment variables. `GEMINI_API_KEY` and `OLLAMA_MODEL` are optional; keys supplied through Telegram are deliberately not accepted or written to SQLite.

Find your numeric Telegram user/chat ID with a trusted ID bot, then set it as `ALLOWED_CHAT_ID`. For a private bot conversation use the numeric private chat ID. The bot silently ignores all other chats.

## Hugging Face Spaces

Create a Gradio Space from this repository, set the Space secrets `TELEGRAM_BOT_TOKEN`, `ALLOWED_CHAT_ID`, and optionally `GEMINI_API_KEY`, and use `app.py` as the entry point. `packages.txt` installs FFmpeg/fonts, and Gradio binds on `0.0.0.0:7860` by default.

**Free-tier caveat:** Spaces may sleep, restart, or impose storage/CPU limits. No free hosting tier can guarantee uninterrupted 24/7 execution. Persistent storage is not guaranteed unless enabled; SQLite/assets can be lost on restart. A keep-alive screen does not override platform sleep policies. For a stable always-on monitor, run on an always-on Linux host.

## Usage

- `/start` opens the inline menu.
- Add a channel/stream page URL from YouTube/Twitch/Kick under “Add 24/7 Live Streamer”.
- Upload a Telegram video (up to `MAX_VIDEO_MB`, default 20MB), or send a supported video URL.
- Set avatar from the menu, or send a photo with caption `/avatar`.
- Add MP3/WAV via “Add Background Beat”.
- Voice button toggles Madhur and Swara. Defaults are `+14%` rate and `+5Hz` pitch.
- Set `WHISPER_MODEL=tiny` if memory is constrained, or `base` for better CPU transcription. Initial model use downloads model files and needs network access.

## Resource and behavior notes

- The worker is deliberately serial and the queue is bounded to 32 jobs to avoid memory/disk spikes. FFmpeg uses `veryfast` and CRF 26.
- Ranking is a transparent RMS + speech-activity heuristic, not a guarantee of virality. Clip title/hook/score are suggestions, not factual claims about reach.
- Gemini free quotas, Edge TTS service availability, and source-site access may change. The offline fallback still lets processing proceed if Gemini is unavailable; if Edge TTS fails, the clip uses its source audio.
- The avatar is composited as an image overlay; this implementation does not claim phoneme-accurate lip sync. FFmpeg subtitles and drawtext require the installed fonts and subtitle libraries.
- Only process content you have permission to download, edit, and redistribute, and follow the source platform's terms.

## Files

- `app.py` — Telegram polling, worker, live monitor, and Gradio status screen.
- `bot/` — configuration, SQLite persistence, monitoring, analysis, script, voice, avatar, editing, and Telegram handlers.
