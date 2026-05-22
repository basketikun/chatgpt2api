from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CAPTCHA_SOLVER_", env_file=".env")

    api_key: str = "change-me"
    # Where chromium profiles (cookies, localStorage) live across restarts.
    data_dir: Path = Path("/data")
    # How many concurrent browser contexts to keep ready in the pool.
    pool_size: int = 2
    # Per-solve timeout (seconds) before we bail.
    solve_timeout: int = 90
    # Display number used by Xvfb; the headful VNC flow attaches here.
    display: str = ":99"
    # Where the noVNC websocket is exposed for the manual-login UX.
    novnc_external_url: str = "http://localhost:6080"


settings = Settings()
