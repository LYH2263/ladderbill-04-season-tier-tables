import json
import sqlite3

COLUMNS = "id, key, name, months, tiers, enabled, created_at, updated_at"


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["months"] = json.loads(d["months"])
    d["tiers"] = json.loads(d["tiers"])
    d["enabled"] = bool(d["enabled"])
    return d


def list_all(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(f"SELECT {COLUMNS} FROM season_schemes ORDER BY key").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_by_key(conn: sqlite3.Connection, key: str) -> dict | None:
    row = conn.execute(f"SELECT {COLUMNS} FROM season_schemes WHERE key=?", (key,)).fetchone()
    return _row_to_dict(row) if row else None


def create(
    conn: sqlite3.Connection,
    key: str,
    name: str,
    months: list[int],
    tiers: list[dict],
    enabled: bool,
) -> dict:
    conn.execute(
        """
        INSERT INTO season_schemes(key, name, months, tiers, enabled, created_at, updated_at)
        VALUES (?,?,?,?,?,datetime('now'),datetime('now'))
        """,
        (key, name, json.dumps(months), json.dumps(tiers, ensure_ascii=False), 1 if enabled else 0),
    )
    conn.commit()
    return get_by_key(conn, key)


def update(
    conn: sqlite3.Connection,
    key: str,
    name: str,
    months: list[int],
    tiers: list[dict],
    enabled: bool,
) -> dict | None:
    cur = conn.execute(
        """
        UPDATE season_schemes SET name=?, months=?, tiers=?, enabled=?, updated_at=datetime('now')
        WHERE key=?
        """,
        (name, json.dumps(months), json.dumps(tiers, ensure_ascii=False), 1 if enabled else 0, key),
    )
    conn.commit()
    if cur.rowcount == 0:
        return None
    return get_by_key(conn, key)


def delete(conn: sqlite3.Connection, key: str) -> bool:
    cur = conn.execute("DELETE FROM season_schemes WHERE key=?", (key,))
    conn.commit()
    return cur.rowcount > 0


def find_month_conflicts(
    conn: sqlite3.Connection, months: list[int], exclude_key: str | None = None
) -> list[dict]:
    """Other enabled schemes already covering any of the given months."""
    conflicts = []
    for row in list_all(conn):
        if not row["enabled"] or row["key"] == exclude_key:
            continue
        for m in sorted(set(row["months"]) & set(months)):
            conflicts.append({"month": m, "scheme_key": row["key"], "scheme_name": row["name"]})
    return conflicts


def find_covering(conn: sqlite3.Connection, month: int) -> dict | None:
    """The enabled scheme covering the given month, if any."""
    for row in list_all(conn):
        if row["enabled"] and month in row["months"]:
            return row
    return None
