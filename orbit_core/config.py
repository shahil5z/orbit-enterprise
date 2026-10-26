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


ENVIRONMENTS = ("local", "dev", "prod")
_LOOPBACK = ("localhost", "127.0.0.1", "0.0.0.0", "::1")


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def _env() -> str:
    e = os.getenv("ORBIT_ENV", "local").strip().lower()
    if e not in ENVIRONMENTS:
        raise RuntimeError(f"ORBIT_ENV must be one of {ENVIRONMENTS}")
    return e


@dataclass(frozen=True)
class Settings:
    env: str = field(default_factory=_env)
    # Hosted Postgres (Neon via Vercel Marketplace) exposes DATABASE_URL; it wins over the discrete fields.
    database_url: str = field(default_factory=lambda: os.getenv("ORBIT_DATABASE_URL") or os.getenv("DATABASE_URL") or "")
    db_host: str = field(default_factory=lambda: os.getenv("ORBIT_DB_HOST", "localhost"))
    db_port: int = field(default_factory=lambda: int(os.getenv("ORBIT_DB_PORT", "55432")))
    db_name: str = field(default_factory=lambda: os.getenv("ORBIT_DB_NAME", "orbit"))
    db_user: str = field(default_factory=lambda: os.getenv("ORBIT_DB_USER", "orbit"))
    db_password: str = field(default_factory=lambda: os.getenv("ORBIT_DB_PASSWORD", ""))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip() for o in os.getenv("ORBIT_CORS_ORIGINS", "http://localhost:5173" if _env() == "local" else "").split(",") if o.strip()
        )
    )
    seed: int = field(default_factory=lambda: int(os.getenv("ORBIT_SEED", "20260101")))
    log_level: str = field(default_factory=lambda: os.getenv("ORBIT_LOG_LEVEL", "INFO"))
    # Julia/Spark/R/Rust/C++/Java only exist on the workstation; hosted deployments serve persisted results.
    local_engines: bool = field(default_factory=lambda: _bool("ORBIT_LOCAL_ENGINES", _env() != "prod"))
    rate_limit_per_min: int = field(default_factory=lambda: int(os.getenv("ORBIT_RATE_LIMIT_PER_MIN", "600")))
    max_body_bytes: int = field(default_factory=lambda: int(os.getenv("ORBIT_MAX_BODY_BYTES", "32768")))

    def problems(self) -> list[str]:
        """Configuration errors that must stop a production start (no secrets in the messages)."""
        if self.env != "prod":
            return []
        out = []
        if any(h in o for o in self.cors_origins for h in _LOOPBACK):
            out.append("ORBIT_CORS_ORIGINS points at a loopback host in prod")
        if not self.database_url:
            out.append("DATABASE_URL is not set in prod")
        elif any(f"@{h}" in self.database_url or f"host={h}" in self.database_url for h in _LOOPBACK):
            out.append("DATABASE_URL points at a loopback host in prod")
        return out

    @property
    def dsn(self) -> str:
        if self.database_url:
            return self.database_url
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
