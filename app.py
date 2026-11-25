"""Process entrypoint: Telegram polling, bounded workers and HTTP health endpoint."""
import asyncio
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from telegram.ext import Application
from bot.config import Settings
from bot.database import Database
from bot.monitor import StreamMonitor
from bot.telegram_handlers import BotService

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("desiclip")

class HealthHandler(BaseHTTPRequestHandler):
    """Minimal health endpoint; no framework or extra worker process required."""
    def do_GET(self):
        if self.path not in ("/", "/health", "/healthz"):
            self.send_response(404)
            self.end_headers()
            return
        payload = b"OK\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        log.debug("health server: " + fmt, *args)

def launch_health_server():
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="health-http", daemon=True).start()
    log.info("HTTP health endpoint listening on port %s", port)
    return server

async def main():
    settings = Settings.from_env()
    settings.prepare_dirs()
    health_server = launch_health_server()
    db = Database(settings.data_dir / "desiclip.sqlite3")
    # Keep queued sources bounded for small containers.
    queue = asyncio.Queue(maxsize=4)
    service = BotService(settings, db, queue)
    app = Application.builder().token(settings.token).build()
    service.register(app)
    monitor = StreamMonitor(db, queue, settings, app)
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
        health_server.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down")
