import json
import sqlite3

PLAN_COLS = "id, code, name, months_json, enabled"


def _row_to_plan(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    tiers = [
        {"id": r["id"], "up_to": r["up_to"], "price": r["price"], "sort_order": r["sort_order"]}
        for r in conn.execute(
            "SELECT id, up_to, price, sort_order FROM season_tiers "
            "WHERE plan_id=? ORDER BY sort_order",
            (row["id"],),
        ).fetchall()
    ]
    return {
        "id": row["id"],
        "code": row["code"],
        "name": row["name"],
        "months": json.loads(row["months_json"]),
        "enabled": bool(row["enabled"]),
        "tiers": tiers,
    }


def list_all(conn: sqlite3.Connection, enabled_only: bool = False) -> list[dict]:
    q = f"SELECT {PLAN_COLS} FROM season_plans"
    if enabled_only:
        q += " WHERE enabled=1"
    q += " ORDER BY id"
    return [_row_to_plan(conn, r) for r in conn.execute(q).fetchall()]


def get_by_id(conn: sqlite3.Connection, plan_id: int) -> dict | None:
    row = conn.execute(f"SELECT {PLAN_COLS} FROM season_plans WHERE id=?", (plan_id,)).fetchone()
    return _row_to_plan(conn, row) if row else None


def get_by_code(conn: sqlite3.Connection, code: str) -> dict | None:
    row = conn.execute(f"SELECT {PLAN_COLS} FROM season_plans WHERE code=?", (code,)).fetchone()
    return _row_to_plan(conn, row) if row else None


def active_for_month(conn: sqlite3.Connection, month: int) -> dict | None:
    """启用方案中生效月份覆盖给定月份的方案；存在多个时取 id 最小者。"""
    rows = conn.execute(
        f"SELECT {PLAN_COLS} FROM season_plans WHERE enabled=1 ORDER BY id"
    ).fetchall()
    for r in rows:
        if month in json.loads(r["months_json"]):
            return _row_to_plan(conn, r)
    return None


def upsert(conn: sqlite3.Connection, plan: dict, plan_id: int | None = None) -> int:
    months_json = json.dumps(sorted(plan["months"]))
    if plan_id is None:
        cur = conn.execute(
            "INSERT INTO season_plans(code, name, months_json, enabled) VALUES (?,?,?,?)",
            (plan["code"], plan["name"], months_json, 1 if plan["enabled"] else 0),
        )
        plan_id = int(cur.lastrowid)
    else:
        conn.execute(
            "UPDATE season_plans SET code=?, name=?, months_json=?, enabled=? WHERE id=?",
            (plan["code"], plan["name"], months_json, 1 if plan["enabled"] else 0, plan_id),
        )
        conn.execute("DELETE FROM season_tiers WHERE plan_id=?", (plan_id,))
    conn.executemany(
        "INSERT INTO season_tiers(plan_id, up_to, price, sort_order) VALUES (?,?,?,?)",
        [
            (plan_id, t["up_to"], t["price"], i + 1)
            for i, t in enumerate(plan["tiers"])
        ],
    )
    conn.commit()
    return plan_id


def delete(conn: sqlite3.Connection, plan_id: int) -> None:
    conn.execute("DELETE FROM season_tiers WHERE plan_id=?", (plan_id,))
    conn.execute("DELETE FROM season_plans WHERE id=?", (plan_id,))
    conn.commit()
