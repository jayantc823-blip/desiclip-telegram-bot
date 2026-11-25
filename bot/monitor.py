"""Periodic yt-dlp live checks and five-minute live capture chunks."""
import asyncio
import logging
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)
SUPPORTED = {"youtube.com", "youtu.be", "twitch.tv", "kick.com"}


def valid_media_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
        return any(host == domain or host.endswith("." + domain) for domain in SUPPORTED)
    except Exception:
        return False

async def ytdlp_info(url: str):
    def work():
        proc = subprocess.run(["yt-dlp", "--no-warnings", "--skip-download", "--dump-single-json", url], capture_output=True, text=True, timeout=90)
        if proc.returncode:
            raise RuntimeError((proc.stderr or "yt-dlp failed")[-500:])
        import json
        return json.loads(proc.stdout)
    return await asyncio.to_thread(work)

async def capture_chunk(url: str, destination: Path, seconds: int = 300):
    info = await ytdlp_info(url)
    stream_url = info.get("url")
    if not stream_url:
        formats = info.get("requested_formats") or info.get("formats") or []
        stream_url = next((f.get("url") for f in reversed(formats) if f.get("url") and f.get("vcodec") != "none"), None)
    if not stream_url:
        raise RuntimeError("No stream URL found")
    # Stream-copy capture avoids a second full encode in this low-memory container.
    proc = await asyncio.create_subprocess_exec("ffmpeg", "-y", "-threads", "1", "-i", stream_url, "-t", str(seconds), "-c", "copy", "-bsf:a", "aac_adtstoasc", str(destination), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    try:
        await asyncio.wait_for(proc.wait(), timeout=seconds + 120)
    except asyncio.TimeoutError:
        proc.kill(); await proc.wait()
    if proc.returncode != 0 or not destination.exists() or destination.stat().st_size < 100_000:
        raise RuntimeError("Live capture yielded no usable chunk")
    return info.get("title") or url

class StreamMonitor:
    def __init__(self, db, queue, settings, app):
        self.db, self.queue, self.settings, self.app = db, queue, settings, app
        self.captures = {}
        self._stop = asyncio.Event()

    async def check_streams(self):
        for streamer in self.db.streamers():
            if not streamer["enabled"]:
                continue
            try:
                info = await ytdlp_info(streamer["url"])
                live = info.get("is_live") is True or info.get("live_status") == "is_live"
                just_went_live = self.db.set_live(streamer["id"], live)
                if live and streamer["id"] not in self.captures:
                    title = info.get("title") or streamer["url"]
                    if just_went_live:
                        await self.app.bot.send_message(self.settings.allowed_chat_id, f"🔴 {title} is LIVE! Auto-clipping started...")
                    task = asyncio.create_task(self._capture_loop(streamer["id"], streamer["url"], title))
                    self.captures[streamer["id"]] = task
                elif not live and streamer["id"] in self.captures:
                    self.captures.pop(streamer["id"]).cancel()
            except Exception as exc:
                log.warning("Live check failed for streamer %s: %s", streamer["id"], exc)

    async def _capture_loop(self, streamer_id, url, title):
        while not self._stop.is_set():
            chunk = self.settings.output_dir / f"live_{streamer_id}_{int(time.time())}.mp4"
            try:
                await capture_chunk(url, chunk, 300)
                await self.queue.put({"path": chunk, "source_title": title, "owned": True})
            except asyncio.CancelledError:
                chunk.unlink(missing_ok=True); raise
            except Exception as exc:
                log.warning("Live chunk capture failed (%s): %s", title, exc)
                chunk.unlink(missing_ok=True)
                await asyncio.sleep(20)

    async def run(self):
        while not self._stop.is_set():
            await self.check_streams()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass

    async def stop(self):
        self._stop.set()
        for task in self.captures.values():
            task.cancel()
        await asyncio.gather(*self.captures.values(), return_exceptions=True)
