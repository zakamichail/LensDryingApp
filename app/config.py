import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{DATA_DIR / 'lens_drying.sqlite3'}",
    )
    secret_key: str = os.getenv("SECRET_KEY", "dev-lens-drying-secret")
    archive_csv_path: Path = DATA_DIR / "test.csv"


settings = Settings()
