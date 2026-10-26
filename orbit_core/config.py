"""Central configuration. Values come from environment variables (optionally a .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


_load_dotenv()


@dataclass(frozen=True)
class Paths:
    root: Path = ROOT
    raw: Path = ROOT / "data" / "raw"
    staging: Path = ROOT / "data" / "staging"
    quarantine: Path = ROOT / "data" / "staging" / "_quarantine"
    curated: Path = ROOT / "data" / "curated"
    samples: Path = ROOT / "data" / "samples"
    outputs: Path = ROOT / "data" / "outputs"
    runs: Path = ROOT / "data" / "runs"
    models: Path = ROOT / "ml" / "artifacts"
    logs: Path = ROOT / "logs"
    tools: Path = ROOT / ".tools"


@dataclass(frozen=True)
class Settings:
    db_host: str = field(default_factory=lambda: os.getenv("ORBIT_DB_HOST", "localhost"))
    db_port: int = field(default_factory=lambda: int(os.getenv("ORBIT_DB_PORT", "55432")))
    db_name: str = field(default_factory=lambda: os.getenv("ORBIT_DB_NAME", "orbit"))
    db_user: str = field(default_factory=lambda: os.getenv("ORBIT_DB_USER", "orbit"))
    db_password: str = field(default_factory=lambda: os.getenv("ORBIT_DB_PASSWORD", ""))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip() for o in os.getenv("ORBIT_CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
        )
    )
    seed: int = field(default_factory=lambda: int(os.getenv("ORBIT_SEED", "20260101")))
    log_level: str = field(default_factory=lambda: os.getenv("ORBIT_LOG_LEVEL", "INFO"))

    @property
    def dsn(self) -> str:
        return (
            f"host={self.db_host} port={self.db_port} dbname={self.db_name} "
            f"user={self.db_user} password={self.db_password}"
        )


PATHS = Paths()
SETTINGS = Settings()


def tool_path(*parts: str) -> Path:
    """Resolve a binary inside the project-local .tools directory."""
    return PATHS.tools.joinpath(*parts)


def ensure_dirs() -> None:
    for p in (PATHS.raw, PATHS.staging, PATHS.quarantine, PATHS.curated, PATHS.samples,
              PATHS.outputs, PATHS.runs, PATHS.models, PATHS.logs):
        p.mkdir(parents=True, exist_ok=True)
