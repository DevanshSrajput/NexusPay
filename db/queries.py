"""Database operations for spend logs and queries."""

from typing import Any, Optional

from db.database import get_connection


async def log_spend(
    query_id: str,
    endpoint: str,
    endpoint_url: str,
    cost_usdc: float,
    txn_hash: Optional[str],
    success: bool,
    error_message: Optional[str] = None,
    data_preview: Optional[str] = None,
) -> int:
    """Insert a single payment attempt. Returns the new row id."""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            """
            INSERT INTO spend_logs
                (query_id, endpoint, endpoint_url, cost_usdc, txn_hash,
                 success, error_message, data_preview)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                query_id,
                endpoint,
                endpoint_url,
                cost_usdc,
                txn_hash,
                1 if success else 0,
                error_message,
                data_preview,
            ),
        )
        await conn.commit()
        return cursor.lastrowid
    finally:
        await conn.close()


async def get_daily_total() -> float:
    """Sum of successful spend for the current UTC day."""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            """
            SELECT COALESCE(SUM(cost_usdc), 0) AS total
            FROM spend_logs
            WHERE success = 1
              AND DATE(created_at) = DATE('now', 'utc')
            """
        )
        row = await cursor.fetchone()
        return float(row["total"]) if row else 0.0
    finally:
        await conn.close()


async def get_all_logs(limit: int = 100) -> list[dict[str, Any]]:
    """All spend logs, newest first."""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT * FROM spend_logs ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def get_logs_by_query(query_id: str) -> list[dict[str, Any]]:
    """All spend logs for one query, oldest first."""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT * FROM spend_logs WHERE query_id = ? ORDER BY created_at ASC, id ASC",
            (query_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def count_queries_today() -> int:
    """Number of queries created in the current UTC day."""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            """
            SELECT COUNT(*) AS c FROM queries
            WHERE DATE(created_at) = DATE('now', 'utc')
            """
        )
        row = await cursor.fetchone()
        return int(row["c"]) if row else 0
    finally:
        await conn.close()


async def create_query(query_id: str, query_text: str, max_spend: float) -> None:
    """Record a new top-level query in 'pending' status."""
    conn = await get_connection()
    try:
        await conn.execute(
            "INSERT INTO queries (id, query_text, max_spend, status) VALUES (?, ?, ?, 'pending')",
            (query_id, query_text, max_spend),
        )
        await conn.commit()
    finally:
        await conn.close()


async def update_query(query_id: str, **fields: Any) -> None:
    """Update arbitrary columns on a query row.

    ``completed_at`` is set automatically when status is terminal.
    """
    if not fields:
        return
    if fields.get("status") in {"complete", "failed"} and "completed_at" not in fields:
        fields["completed_at"] = None  # placeholder, set via SQL below

    assignments = []
    values: list[Any] = []
    for key, val in fields.items():
        if key == "completed_at" and val is None and fields.get("status") in {"complete", "failed"}:
            assignments.append("completed_at = datetime('now', 'utc')")
            continue
        assignments.append(f"{key} = ?")
        values.append(val)
    values.append(query_id)

    conn = await get_connection()
    try:
        await conn.execute(
            f"UPDATE queries SET {', '.join(assignments)} WHERE id = ?",
            values,
        )
        await conn.commit()
    finally:
        await conn.close()
