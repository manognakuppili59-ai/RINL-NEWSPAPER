"""
Application configuration.

All settings are read from environment variables (via .env in development).
Nothing is hardcoded here so the same code runs in dev / staging / prod
by just swapping the .env file.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- General ---
    APP_NAME: str = "NewsPulse API"
    APP_ENV: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # --- CORS ---
    # The React dev server (Vite) runs on 5173 by default.
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    # --- Database (MySQL) ---
    # Not yet used to run queries on Day 1 — reserved for when
    # models/CRUD are implemented.
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "changeme"
    DB_NAME: str = "newspulse"

    # --- Auth ---
    SECRET_KEY: str = "changeme-in-env"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    # Used instead of ACCESS_TOKEN_EXPIRE_MINUTES when the user checks
    # "Keep me signed in" on the login form.
    REMEMBER_ME_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    ADMIN_PASSWORD: str = "changeme"

    # --- Outbound email (forgot-password) ---
    # If SMTP_HOST is left blank, the app falls back to logging the reset
    # link to the console instead of emailing it — so registration/login/
    # forgot-password all still work out of the box with zero mail setup.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_FROM_EMAIL: str = "no-reply@newspulse.local"
    SMTP_FROM_NAME: str = "NewsPulse"

    @property
    def SMTP_CONFIGURED(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_USER and self.SMTP_PASSWORD)

    # --- News providers ---
    # Primary: GNews (https://gnews.io) — free tier, sign up for a key.
    # Secondary: NewsData.io (https://newsdata.io) — free tier, sign up for a key.
    # Fallback: Google News RSS — no key needed, always active.
    # Leave either key blank to skip straight past that provider.
    GNEWS_API_KEY: str = ""
    NEWSDATA_API_KEY: str = ""

    # --- Report generation ---
    # Where generated PDFs are written, relative to the backend/ folder
    # unless given as an absolute path. Created automatically on startup.
    REPORTS_DIR: str = "generated_reports"

    @property
    def DATABASE_URL(self) -> str:
        # Using SQLite for local testing instead of MySQL
        import os
        from pathlib import Path
        db_path = Path(__file__).resolve().parent.parent.parent / "test.db"
        return f"sqlite:///{db_path}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
