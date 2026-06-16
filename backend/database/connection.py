import os
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy import event, text


def load_env_files() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for env_path in (repo_root / ".env", repo_root / "backend" / ".env"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def default_database_url() -> str:
    if os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        return "sqlite+aiosqlite:////tmp/claims.db"
    return "sqlite+aiosqlite:///claims.db"


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


load_env_files()
DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", default_database_url()))
print(DATABASE_URL)

def is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith(("sqlite+aiosqlite://", "sqlite://"))


def ensure_sqlite_parent_directory(database_url: str) -> None:
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    for prefix in prefixes:
        if not database_url.startswith(prefix):
            return
        database_path = database_url.removeprefix(prefix)
        if database_path.startswith("/"):
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        return


ensure_sqlite_parent_directory(DATABASE_URL)

engine_kwargs = {"echo": False}
if is_sqlite_url(DATABASE_URL):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(
    DATABASE_URL,
    **engine_kwargs,
)

if is_sqlite_url(DATABASE_URL):
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def init_db():
    from backend.database import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_claims_member_id ON claims(member_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_claims_policy_id ON claims(policy_id)"))
        if is_sqlite_url(DATABASE_URL):
            await ensure_column(conn, "llm_metrics", "input_tokens", "INTEGER NOT NULL DEFAULT 0")
            await ensure_column(conn, "llm_metrics", "output_tokens", "INTEGER NOT NULL DEFAULT 0")
            await ensure_column(conn, "llm_metrics", "total_tokens", "INTEGER NOT NULL DEFAULT 0")
    from backend.database.seed import seed_policy_data

    await seed_policy_data()


async def ensure_column(conn, table_name: str, column_name: str, column_definition: str) -> None:
    result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
    existing_columns = {row[1] for row in result.fetchall()}
    if column_name not in existing_columns:
        await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"))
