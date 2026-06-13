"""SQLite connection management and schema initialization."""

import aiosqlite

from config.settings import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS spend_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id        TEXT NOT NULL,
    endpoint        TEXT NOT NULL,
    endpoint_url    TEXT NOT NULL,
    cost_usdc       REAL NOT NULL,
    txn_hash        TEXT,
    success         INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT,
    data_preview    TEXT,
    quality_rating  REAL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

CREATE INDEX IF NOT EXISTS idx_spend_logs_date ON spend_logs (created_at);
CREATE INDEX IF NOT EXISTS idx_spend_logs_query ON spend_logs (query_id);

CREATE TABLE IF NOT EXISTS queries (
    id                TEXT PRIMARY KEY,
    query_text        TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    max_spend         REAL NOT NULL,
    estimated_cost    REAL,
    actual_cost       REAL,
    sources_planned   TEXT,
    sources_used      TEXT,
    planner_reasoning TEXT,
    final_answer      TEXT,
    error_message     TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    completed_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_queries_status ON queries (status);
"""


async def get_connection() -> aiosqlite.Connection:
    """Open a new connection with row access by column name."""
    conn = await aiosqlite.connect(settings.db_path)
    conn.row_factory = aiosqlite.Row
    return conn


async def init_db() -> None:
    """Create tables and indexes if they do not exist. Call once on startup."""
    async with aiosqlite.connect(settings.db_path) as conn:
        await conn.executescript(SCHEMA)
        await conn.commit()
