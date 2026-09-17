import json

from app.db import connect
from app.engines.peak_compare import compare_plain_vs_peak
from app.engines.tier_progressive import calc_bill

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS accounts(
    id INTEGER PRIMARY KEY, name TEXT, meter_no TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS readings(id INTEGER PRIMARY KEY, account_id INTEGER, kwh REAL, peak INTEGER);
CREATE TABLE IF NOT EXISTS tiers(id INTEGER PRIMARY KEY, up_to REAL, price REAL, sort_order INTEGER);
CREATE TABLE IF NOT EXISTS calc_runs(
    id INTEGER PRIMARY KEY,
    kind TEXT,
    account_id INTEGER,
    input_json TEXT,
    result_json TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS season_plans(
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE,
    name TEXT,
    months_json TEXT,
    enabled INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS season_tiers(
    id INTEGER PRIMARY KEY,
    plan_id INTEGER,
    up_to REAL,
    price REAL,
    sort_order INTEGER
);
"""


def init_db():
    conn = connect()
    conn.executescript(SCHEMA_SQL)
    if conn.execute("SELECT COUNT(*) c FROM accounts").fetchone()["c"] == 0:
        conn.execute(
            "INSERT INTO accounts(name, meter_no, note) VALUES ('张家', 'M-1001', '对照：正常用量')"
        )
        conn.execute(
            "INSERT INTO accounts(name, meter_no, note) VALUES ('李家(种子偏高)', 'M-1002', '对照：高用量+尖峰')"
        )
        conn.executemany(
            "INSERT INTO tiers(up_to, price, sort_order) VALUES (?,?,?)",
            [(180, 0.52, 1), (260, 0.62, 2), (None, 0.82, 3)],
        )
        conn.execute("INSERT INTO readings(account_id, kwh, peak) VALUES (1, 120, 0)")
        conn.execute("INSERT INTO readings(account_id, kwh, peak) VALUES (2, 400, 1)")
        conn.execute("INSERT INTO settings(key, value) VALUES ('peak_factor', '1.2')")
        conn.execute("INSERT INTO settings(key, value) VALUES ('currency', 'CNY')")
        tiers = [{"up_to": r[0], "price": r[1]} for r in [(180, 0.52), (260, 0.62), (None, 0.82)]]
        bill1 = calc_bill(120, tiers, 1.0)
        conn.execute(
            "INSERT INTO calc_runs(kind, account_id, input_json, result_json, created_at) VALUES (?,?,?,?,datetime('now'))",
            ("bill", 1, json.dumps({"kwh": 120, "peak": False}), json.dumps(bill1, ensure_ascii=False)),
        )
        cmp2 = compare_plain_vs_peak(400, tiers, 1.2)
        conn.execute(
            "INSERT INTO calc_runs(kind, account_id, input_json, result_json, created_at) VALUES (?,?,?,?,datetime('now'))",
            ("compare", 2, json.dumps({"kwh": 400}), json.dumps(cmp2, ensure_ascii=False)),
        )
        # 季节档表：丰水期(6-10月)电价下浮；枯水期(1,2,11,12月)电价上浮；
        # 3-5 月无命中，回退全局默认 tiers。两套启用方案月份互不相交。
        conn.execute(
            "INSERT INTO season_plans(code, name, months_json, enabled) VALUES (?,?,?,1)",
            ("wet", "丰水期", json.dumps([6, 7, 8, 9, 10])),
        )
        conn.executemany(
            "INSERT INTO season_tiers(plan_id, up_to, price, sort_order) VALUES (?,?,?,?)",
            [(1, 180, 0.45, 1), (1, 260, 0.55, 2), (1, None, 0.70, 3)],
        )
        conn.execute(
            "INSERT INTO season_plans(code, name, months_json, enabled) VALUES (?,?,?,1)",
            ("dry", "枯水期", json.dumps([1, 2, 11, 12])),
        )
        conn.executemany(
            "INSERT INTO season_tiers(plan_id, up_to, price, sort_order) VALUES (?,?,?,?)",
            [(2, 180, 0.58, 1), (2, 260, 0.68, 2), (2, None, 0.90, 3)],
        )
        conn.commit()
    conn.close()
