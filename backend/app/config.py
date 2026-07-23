from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _BACKEND_DIR.parent

# Look in the project root first (where .env.example and docker-compose expect
# it) and then in backend/. Resolving from the module rather than the working
# directory means the key is found however the server was launched. Later files
# win, so a backend/.env can override the shared one.
ENV_FILES = (_PROJECT_ROOT / ".env", _BACKEND_DIR / ".env")


class Settings(BaseSettings):
    """App settings from environment / .env (CLIPFORGE_ prefix)."""

    model_config = SettingsConfigDict(
        env_prefix="CLIPFORGE_", env_file=ENV_FILES, extra="ignore"
    )

    data_dir: Path = Path("./data")
    database_url: str = "sqlite+aiosqlite:///./data/clipforge.db"
    cors_origins: str = "http://localhost:3000"
    max_upload_bytes: int = 16 * 1024**3

    # Burned-in label font. Auto-detected when empty.
    font_file: str = ""

    # Transcription (only needed when AI titles are enabled)
    whisper_enabled: bool = True
    whisper_model: str = "base"
    whisper_device: str = "cpu"

    # Groq (free tier) — https://console.groq.com/keys
    groq_model: str = "llama-3.3-70b-versatile"
    groq_stt_model: str = "whisper-large-v3-turbo"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def parts_dir(self) -> Path:
        return self.data_dir / "parts"

    @property
    def thumbs_dir(self) -> Path:
        return self.data_dir / "thumbnails"

    @property
    def credentials_dir(self) -> Path:
        return self.data_dir / "credentials"

    @property
    def default_output_dir(self) -> Path:
        return self.data_dir / "output"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        for d in (
            self.uploads_dir,
            self.parts_dir,
            self.thumbs_dir,
            self.credentials_dir,
            self.default_output_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


class _Secrets(BaseSettings):
    """Keys that keep their conventional names (no CLIPFORGE_ prefix)."""

    model_config = SettingsConfigDict(env_file=ENV_FILES, extra="ignore")

    groq_api_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/drive/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_secrets() -> _Secrets:
    return _Secrets()
