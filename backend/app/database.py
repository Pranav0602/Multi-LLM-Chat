"""SQLAlchemy engine / session / Base."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings


def _normalized_db_url(url: str) -> str:
    """Belt-and-suspenders: never pass postgres:// to SQLAlchemy 2.x."""
    if not url:
        return "sqlite:///./research_chat.db"
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


db_url = _normalized_db_url(settings.DATABASE_URL)
connect_args = {}
if db_url.startswith("sqlite"):
    # Required for SQLite + FastAPI threads.
    connect_args = {"check_same_thread": False}

engine = create_engine(db_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_chat_type_column() -> None:
    """Safe conditional migration for SQLite/Postgres backwards compatibility.

    Adds `conversations.chat_type` if missing without touching existing rows.
    Existing rows keep the SQLAlchemy column default ("research") on read;
    we backfill NULL/empty values defensively.
    """
    from sqlalchemy import inspect, text

    try:
        insp = inspect(engine)
        if "conversations" not in insp.get_table_names():
            return
        cols = {c["name"] for c in insp.get_columns("conversations")}
        if "chat_type" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE conversations ADD COLUMN chat_type VARCHAR(64) DEFAULT 'research'"))
        # Backfill any legacy NULL/empty values.
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE conversations SET chat_type='research' WHERE chat_type IS NULL OR chat_type=''")
            )
    except Exception:
        # Migration is best-effort; a fresh create_all() covers new DBs.
        pass
