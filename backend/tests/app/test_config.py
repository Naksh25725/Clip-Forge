import os
from pathlib import Path

import pytest
from pydantic_settings import BaseSettings

from backend.app import config
from backend.app.config import Settings, _Secrets, get_settings, get_secrets


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """Ensure tests don't read actual .env files or get polluted by host env vars."""
    # Prevent loading actual .env files
    monkeypatch.setattr(config, "ENV_FILES", ())

    # Clear out any existing CLIPFORGE_ or secret env vars
    for key in list(os.environ.keys()):
        if key.startswith("CLIPFORGE_") or key in [
            "GROQ_API_KEY",
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "GOOGLE_REDIRECT_URI",
        ]:
            monkeypatch.delenv(key, raising=False)

    # Clear lru_cache for get_settings and get_secrets
    get_settings.cache_clear()
    get_secrets.cache_clear()

    yield

    # Clear again after tests
    get_settings.cache_clear()
    get_secrets.cache_clear()


def test_settings_defaults():
    settings = Settings()
    assert settings.data_dir == Path("./data")
    assert settings.whisper_enabled is True
    assert settings.groq_model == "llama-3.3-70b-versatile"
    assert settings.cors_origins == "http://localhost:3000"


def test_settings_override_env_vars(monkeypatch):
    monkeypatch.setenv("CLIPFORGE_DATA_DIR", "/tmp/clipforge_data")
    monkeypatch.setenv("CLIPFORGE_WHISPER_ENABLED", "false")
    monkeypatch.setenv("CLIPFORGE_CORS_ORIGINS", "http://test1.com, http://test2.com")

    settings = Settings()

    assert settings.data_dir == Path("/tmp/clipforge_data")
    assert settings.whisper_enabled is False
    assert settings.cors_origins == "http://test1.com, http://test2.com"
    assert settings.cors_origin_list == ["http://test1.com", "http://test2.com"]


def test_settings_cors_origin_list_handling(monkeypatch):
    # Test handling of extra spaces and empty strings
    monkeypatch.setenv("CLIPFORGE_CORS_ORIGINS", " http://a.com ,  , http://b.com  ")
    settings = Settings()
    assert settings.cors_origin_list == ["http://a.com", "http://b.com"]


def test_settings_properties():
    settings = Settings(data_dir=Path("/base/dir"))

    assert settings.uploads_dir == Path("/base/dir/uploads")
    assert settings.parts_dir == Path("/base/dir/parts")
    assert settings.thumbs_dir == Path("/base/dir/thumbnails")
    assert settings.credentials_dir == Path("/base/dir/credentials")
    assert settings.default_output_dir == Path("/base/dir/output")


def test_settings_ensure_dirs(tmp_path):
    settings = Settings(data_dir=tmp_path)

    # Directories shouldn't exist initially
    assert not settings.uploads_dir.exists()
    assert not settings.parts_dir.exists()

    settings.ensure_dirs()

    # Directories should be created
    assert settings.uploads_dir.exists()
    assert settings.uploads_dir.is_dir()
    assert settings.parts_dir.exists()
    assert settings.thumbs_dir.exists()
    assert settings.credentials_dir.exists()
    assert settings.default_output_dir.exists()


def test_secrets_defaults():
    secrets = _Secrets()
    assert secrets.groq_api_key == ""
    assert secrets.google_client_id == ""
    assert secrets.google_client_secret == ""
    assert secrets.google_redirect_uri == "http://localhost:8000/api/drive/callback"


def test_secrets_override_env_vars(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test_groq_key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_client_id")

    secrets = _Secrets()
    assert secrets.groq_api_key == "test_groq_key"
    assert secrets.google_client_id == "test_client_id"


def test_get_settings_caching():
    settings_1 = get_settings()
    settings_2 = get_settings()

    assert settings_1 is settings_2  # Should be the exact same object
    assert settings_1.data_dir == Path("./data")


def test_get_secrets_caching():
    secrets_1 = get_secrets()
    secrets_2 = get_secrets()

    assert secrets_1 is secrets_2  # Should be the exact same object
