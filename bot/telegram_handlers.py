"""Private Telegram UX, inline menus and the background clip-processing queue."""
import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from . import analyzer, avatar_engine, desi_scriptwriter, editor, monitor, voice_engine

log = logging.getLogger(__name__)
MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("🔴 Add 24/7 Live Streamer", callback_data="add")],
    [InlineKeyboardButton("📋 My Streamers", callback_data="list")],
    [InlineKeyboardButton("🎭 Set AI Avatar Face", callback_data="avatar")],
    [InlineKeyboardButton("🎵 Add Background Beat", callback_data="bgm")],
    [InlineKeyboardButton("🗣️ Change Desi Voice", callback_data="voice")],
    [InlineKeyboardButton("📊 Queue & System Status", callback_data="status")],
])

class BotService:
    def __init__(self, settings, db, queue):
        self.settings, self.db, self.queue = settings, db, queue
        self.active = set()
        self.voice = "hi-IN-MadhurNeural"

    def allowed(self, update: Update):
        return bool(update.effective_chat and update.effective_chat.id == self.settings.allowed_chat_id)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.allowed(update): return
        await update.effective_message.reply_text("Namaste! DesiClip is ready. Send a supported video URL or upload a video to queue it.", reply_markup=MENU)

    async def callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not self.allowed(update):
            await query.answer("Not authorized", show_alert=True); return
        await query.answer()
        action = query.data
        if action == "add":
            context.user_data["await"] = "stream"
            await query.message.reply_text("Send a YouTube, Twitch, or Kick channel/stream URL.")
        elif action == "list":
            rows = self.db.streamers()
            if not rows:
                await query.message.reply_text("No streamers saved yet.", reply_markup=MENU); return
            for row in rows:
                status = "🔴 LIVE" if row["last_live"] else "⚪ Watching"
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Remove", callback_data=f"remove:{row['id']}")]])
                await query.message.reply_text(f"{status} · {row['title']}\n{row['url']}", reply_markup=keyboard)
        elif action.startswith("remove:"):
            try: removed = self.db.remove_streamer(int(action.split(":", 1)[1]))
            except ValueError: removed = False
            await query.message.reply_text("Streamer removed." if removed else "Streamer not found.", reply_markup=MENU)
        elif action in ("avatar", "bgm"):
            context.user_data["await"] = action
            await query.message.reply_text("Send a photo." if action == "avatar" else "Send an MP3 or WAV audio file.")
        elif action == "voice":
            self.voice = "hi-IN-SwaraNeural" if self.voice == "hi-IN-MadhurNeural" else "hi-IN-MadhurNeural"
            await query.message.reply_text(f"Voice set to {self.voice} (rate +14%, pitch +5Hz). Tap again to toggle.", reply_markup=MENU)
        elif action == "status":
            await query.message.reply_text(self.status_text(), reply_markup=MENU)
        elif action == "menu":
            await query.message.reply_text("Main menu", reply_markup=MENU)

    def status_text(self):
        disk = shutil.disk_usage(self.settings.output_dir)
        try:
            import psutil
            ram = psutil.virtual_memory()
            ram_text = f"{ram.available / 1024**3:.1f} GB free RAM"
        except Exception:
            ram_text = "RAM details unavailable (install psutil)"
        return f"Queue: {self.queue.qsize()} pending · {len(self.active)} processing\n{ram_text}\nDisk: {disk.free / 1024**3:.1f} GB free\nClips delivered: {self.db.clip_count()}"

    async def text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.allowed(update): return
        text = (update.effective_message.text or "").strip()
        intent = context.user_data.pop("await", None)
        if intent == "stream":
            if not monitor.valid_media_url(text):
                await update.effective_message.reply_text("Please send a YouTube, Twitch, or Kick URL."); return
            try:
                info = await monitor.ytdlp_info(text)
                self.db.add_streamer(text, info.get("title") or text)
                await update.effective_message.reply_text("✅ Added to the live watchlist.", reply_markup=MENU)
            except Exception as exc:
                await update.effective_message.reply_text(f"Could not inspect URL: {str(exc)[:250]}")
            return
        if monitor.valid_media_url(text):
            await update.effective_message.reply_text("⏳ Queued! Finding viral moments...")
            await self.queue.put({"url": text, "source_title": text, "owned": True})
        else:
            await update.effective_message.reply_text("Send a supported video URL, upload a video, or use /start for the menu.", reply_markup=MENU)

    async def media(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.allowed(update): return
        message = update.effective_message
        intent = context.user_data.pop("await", None)
        if message.photo and (intent == "avatar" or message.caption == "/avatar"):
            photo = await message.photo[-1].get_file()
            temp = self.settings.output_dir / f"avatar_in_{update.effective_user.id}.jpg"
            await photo.download_to_drive(temp)
            target = self.settings.assets_dir / "avatar" / "active.jpg"
            try:
                await avatar_engine.validate_and_store(temp, target)
                await message.reply_text("✅ Avatar updated.", reply_markup=MENU)
            except Exception as exc:
                await message.reply_text(str(exc))
            finally: temp.unlink(missing_ok=True)
            return
        if message.audio or message.document and (message.document.mime_type or "").startswith("audio/"):
            obj = message.audio or message.document
            if intent != "bgm" and Path(obj.file_name or "audio.mp3").suffix.lower() not in (".mp3", ".wav"):
                await message.reply_text("Use Add Background Beat first, then send an MP3 or WAV."); return
            suffix = Path(obj.file_name or "bgm.mp3").suffix.lower()
            if suffix not in (".mp3", ".wav"): suffix = ".mp3"
            target = self.settings.assets_dir / "bgm" / ("active" + suffix)
            tgfile = await obj.get_file(); await tgfile.download_to_drive(target)
            for old in ("active.mp3", "active.wav"):
                old_path = self.settings.assets_dir / "bgm" / old
                if old_path != target: old_path.unlink(missing_ok=True)
            await message.reply_text("✅ Background beat saved.", reply_markup=MENU); return
        if message.video or message.document and (message.document.mime_type or "").startswith("video/"):
            obj = message.video or message.document
            if (obj.file_size or 0) > self.settings.max_video_mb * 1024 * 1024:
                await message.reply_text(f"File exceeds the {self.settings.max_video_mb} MB configured limit. Send a supported video URL instead."); return
            suffix = Path(obj.file_name or "upload.mp4").suffix.lower()
            if suffix not in (".mp4", ".mov", ".m4v", ".webm"): suffix = ".mp4"
            path = self.settings.output_dir / f"upload_{message.message_id}{suffix}"
            await (await obj.get_file()).download_to_drive(path)
            await message.reply_text("⏳ Queued! Finding viral moments...")
            await self.queue.put({"path": path, "source_title": obj.file_name or "Telegram video", "owned": True})
            return
        if message.photo:
            await message.reply_text("For avatar update, use Set AI Avatar Face or send the photo with caption /avatar.")

    async def worker(self, app: Application):
        while True:
            job = await self.queue.get()
            source = job.get("path")
            root = Path(tempfile.mkdtemp(prefix="desiclip_", dir=self.settings.output_dir))
            self.active.add(str(root))
            try:
                if not source:
                    source = root / "source.mp4"
                    await self._download(job["url"], source)
                source = Path(source)
                candidates = await analyzer.analyze(source, root, self.settings.clip_seconds, self.settings.whisper_model)
                if not candidates:
                    raise RuntimeError("No usable video/audio detected")
                for index, candidate in enumerate(candidates, 1):
                    script = await desi_scriptwriter.make_script(candidate["transcript"], self.settings.gemini_api_key, self.settings.ollama_model, self.settings.ollama_base_url)
                    voice = root / f"voice_{index}.mp3"
                    voice_path = await voice_engine.synthesize(script["voiceover"], voice, self.voice)
                    output = root / f"clip_{index}.mp4"
                    avatar = self.settings.assets_dir / "avatar" / "active.jpg"
                    bgm = next(iter((self.settings.assets_dir / "bgm").glob("active.*")), None)
                    await editor.render(source, output, root, candidate["start"], candidate["end"], script, voice_path, avatar if avatar.exists() else None, bgm)
                    caption = f"🎬 {script['title']}\n🪝 {script['hook']}\n📈 Heuristic score: {candidate['score']}/99\n{script['hashtags']}"
                    with output.open("rb") as video:
                        await app.bot.send_video(self.settings.allowed_chat_id, video=video, caption=caption[:1024], supports_streaming=True)
                    self.db.increment_clips()
            except Exception as exc:
                log.exception("Clip job failed")
                try: await app.bot.send_message(self.settings.allowed_chat_id, f"⚠️ Clip job failed: {str(exc)[:500]}")
                except Exception: pass
            finally:
                self.active.discard(str(root))
                # Clean the job's downloaded/uploaded source only after processing has stopped.
                if job.get("owned") and source:
                    try: Path(source).unlink(missing_ok=True)
                    except OSError: pass
                shutil.rmtree(root, ignore_errors=True)
                self.queue.task_done()

    async def _download(self, url: str, destination: Path):
        proc = await asyncio.create_subprocess_exec("yt-dlp", "--no-playlist", "--max-filesize", f"{self.settings.max_video_mb}M", "-f", "bv*[height<=1080]+ba/b[height<=1080]", "--merge-output-format", "mp4", "-o", str(destination), url, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError((err or b"yt-dlp download failed").decode(errors="replace")[-500:])
        if not destination.exists():
            # yt-dlp may append a container extension to a template without one.
            matches = list(destination.parent.glob(destination.name + ".*"))
            if matches: matches[0].replace(destination)
        if not destination.exists(): raise RuntimeError("Download completed without an output file")

    def register(self, app: Application):
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CallbackQueryHandler(self.callback))
        app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.ATTACHMENT, self.media))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text))
