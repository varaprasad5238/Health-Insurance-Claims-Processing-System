from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy import event, text

DATABASE_URL = "sqlite+aiosqlite:///claims.db"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False}
)

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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_claims_member_id ON claims(member_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_claims_policy_id ON claims(policy_id)"))
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
