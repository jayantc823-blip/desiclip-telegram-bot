"""Environment-backed configuration. Secrets are never persisted by the bot."""
from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    token: str
    allowed_chat_id: int
    gemini_api_key: str
    ollama_model: str
    ollama_base_url: str
    data_dir: Path
    assets_dir: Path
    output_dir: Path
    whisper_model: str
    max_video_mb: int
    clip_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("ALLOWED_CHAT_ID", "").strip()
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required (set it in .env or deployment secrets).")
        if not chat_id or not chat_id.lstrip("-").isdigit():
            raise RuntimeError("ALLOWED_CHAT_ID must be your numeric Telegram chat ID.")
        return cls(
            token=token,
            allowed_chat_id=int(chat_id),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            ollama_model=os.getenv("OLLAMA_MODEL", "").strip(),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            data_dir=Path(os.getenv("DATA_DIR", "./data")),
            assets_dir=Path(os.getenv("ASSETS_DIR", "./assets")),
            output_dir=Path(os.getenv("OUTPUT_DIR", "./work")),
            whisper_model=os.getenv("WHISPER_MODEL", "base"),
            max_video_mb=max(1, int(os.getenv("MAX_VIDEO_MB", "20"))),
            clip_seconds=max(15, min(60, int(os.getenv("CLIP_SECONDS", "38")))),
        )

    def prepare_dirs(self) -> None:
        for path in (self.data_dir, self.assets_dir / "bgm", self.assets_dir / "avatar", self.output_dir):
            path.mkdir(parents=True, exist_ok=True)
