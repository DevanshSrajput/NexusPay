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
    quality_rating: Optional[float] = None,
) -> int:
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            """
            INSERT INTO spend_logs
                (query_id, endpoint, endpoint_url, cost_usdc, txn_hash,
                 success, error_message, data_preview, quality_rating)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                quality_rating,
            ),
        )
        await conn.commit()
        return cursor.lastrowid
    finally:
        await conn.close()


async def get_daily_total() -> float:
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
    conn = await get_connection()
    try:
        await conn.execute(
            "INSERT INTO queries (id, query_text, max_spend, status) VALUES (?, ?, ?, 'pending')",
            (query_id, query_text, max_spend),
        )
        await conn.commit()
    finally:
        await conn.close()


_UPDATABLE_QUERY_COLUMNS = frozenset({
    "status", "max_spend", "estimated_cost", "actual_cost",
    "sources_planned", "sources_used", "planner_reasoning",
    "final_answer", "error_message", "completed_at",
})

_TERMINAL_STATUSES = {"complete", "partial", "failed"}


async def update_query(query_id: str, **fields: Any) -> None:
    if not fields:
        return

    unknown = set(fields) - _UPDATABLE_QUERY_COLUMNS
    if unknown:
        raise ValueError(f"update_query received unknown column(s): {sorted(unknown)}")

    if fields.get("status") in _TERMINAL_STATUSES and "completed_at" not in fields:
        fields["completed_at"] = None

    assignments = []
    values: list[Any] = []
    for key, val in fields.items():
        if key == "completed_at" and val is None:
            assignments.append(f"{key} = datetime('now', 'utc')")
        else:
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
