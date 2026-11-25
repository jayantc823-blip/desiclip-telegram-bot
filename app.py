"""Process entrypoint: Telegram polling, bounded workers, live monitor, optional Gradio."""
import asyncio
import logging
import os
import threading
import gradio as gr
from telegram.ext import Application
from bot.config import Settings
from bot.database import Database
from bot.monitor import StreamMonitor
from bot.telegram_handlers import BotService

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("desiclip")

def launch_status():
    # Minimal informational page for Spaces. All controls remain in Telegram.
    demo = gr.Interface(fn=lambda: "DesiClip worker is running. Use Telegram /start to control the bot.", inputs=None, outputs=gr.Textbox(label="Service status"), title="DesiClip Telegram Bot", allow_flagging="never")
    demo.launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", "7860")), share=False, quiet=True, prevent_thread_lock=True)

async def main():
    settings = Settings.from_env()
    settings.prepare_dirs()
    db = Database(settings.data_dir / "desiclip.sqlite3")
    queue = asyncio.Queue(maxsize=32)
    service = BotService(settings, db, queue)
    app = Application.builder().token(settings.token).build()
    service.register(app)
    monitor = StreamMonitor(db, queue, settings, app)
    threading.Thread(target=launch_status, name="gradio-status", daemon=True).start()
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    worker = asyncio.create_task(service.worker(app), name="clip-worker")
    watcher = asyncio.create_task(monitor.run(), name="live-monitor")
    log.info("DesiClip started; authorized chat ID is configured.")
    try:
        await asyncio.gather(worker, watcher)
    finally:
        await monitor.stop()
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down")
