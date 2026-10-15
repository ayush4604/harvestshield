from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))


def today_ist():
    return datetime.now(IST).date()


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    artifacts_dir: Path
    environment: str = "local"
    read_only: bool = False
    admin_token: str = field(default="", repr=False)
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "backend", "testserver")

    def __post_init__(self):
        if self.environment not in ("local", "production"):
            raise ValueError("HARVESTSHIELD_ENV must be local or production.")
        if self.environment == "production" and not self.read_only and len(self.admin_token) < 32:
            raise ValueError("Production writes require an admin token of at least 32 characters.")
        if self.environment == "production" and (not self.allowed_hosts or "*" in self.allowed_hosts):
            raise ValueError("Production requires explicit allowed host names, not a wildcard.")

    @classmethod
    def default(cls):
        data_dir = Path(os.getenv("HARVESTSHIELD_DATA_DIR") or PROJECT_ROOT / "data")
        environment = os.getenv("HARVESTSHIELD_ENV", "local").lower()
        raw_read_only = os.getenv("HARVESTSHIELD_READ_ONLY", "true" if environment == "production" else "false").lower()
        if raw_read_only not in ("true", "false"):
            raise ValueError("HARVESTSHIELD_READ_ONLY must be true or false.")
        hosts = tuple(h.strip() for h in os.getenv("HARVESTSHIELD_ALLOWED_HOSTS", "localhost,127.0.0.1,backend,testserver").split(",") if h.strip())
        return cls(data_dir, data_dir.parent / "artifacts" if data_dir.name == "data" else data_dir / "artifacts",
                   environment, raw_read_only == "true", os.getenv("HARVESTSHIELD_ADMIN_TOKEN", ""), hosts)

    def prepare(self):
        for path in (self.data_dir, self.artifacts_dir, self.data_dir / "imports"):
            path.mkdir(parents=True, exist_ok=True)
