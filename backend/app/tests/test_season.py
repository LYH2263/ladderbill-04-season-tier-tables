import sqlite3

import pytest

from app.seed import SCHEMA_SQL
from app.services.billing_service import BillingService
from app.services.season_service import (
    REASON_MATCHED,
    REASON_NO_ENABLED_PLAN,
    REASON_NO_MATCH,
    SeasonConflictError,
    SeasonService,
)

WET_TIERS = [
    {"up_to": 180, "price": 0.45},
    {"up_to": 260, "price": 0.55},
    {"up_to": None, "price": 0.70},
]
DRY_TIERS = [
    {"up_to": 180, "price": 0.58},
    {"up_to": 260, "price": 0.68},
    {"up_to": None, "price": 0.90},
]
DEFAULT_TIERS = [
    {"up_to": 180, "price": 0.52},
    {"up_to": 260, "price": 0.62},
    {"up_to": None, "price": 0.82},
]


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA_SQL)
    c.executemany(
        "INSERT INTO tiers(up_to, price, sort_order) VALUES (?,?,?)",
        [(180, 0.52, 1), (260, 0.62, 2), (None, 0.82, 3)],
    )
    c.execute("INSERT INTO settings(key, value) VALUES ('peak_factor', '1.2')")
    c.commit()
    yield c
    c.close()


def _plan(code, name, months, tiers, enabled=True):
    return {"code": code, "name": name, "months": months, "enabled": enabled, "tiers": tiers}


def _save(conn, *plans):
    svc = SeasonService(conn)
    for p in plans:
        svc.save_plan(p)


# ---------- 冲突检测 ----------

def test_overlapping_enabled_plans_rejected_with_month_and_code(conn):
    svc = SeasonService(conn)
    svc.save_plan(_plan("wet", "丰水期", [6, 7, 8, 9, 10], WET_TIERS))
    bad = _plan("summer", "夏季", [9, 10, 11], DRY_TIERS)
    with pytest.raises(SeasonConflictError) as ei:
        svc.save_plan(bad)
    conflicts = {(c["month"], c["with_code"]) for c in ei.value.conflicts}
    assert conflicts == {(9, "wet"), (10, "wet")}
    # 冲突方案未落库
    from app.repositories import season_plans as plans_repo

    assert plans_repo.get_by_code(conn, "summer") is None


def test_update_self_does_not_conflict(conn):
    svc = SeasonService(conn)
    wet = svc.save_plan(_plan("wet", "丰水期", [6, 7, 8, 9, 10], WET_TIERS))
    # 改名/改阶梯，月份与自身相交不应报错
    updated = svc.save_plan(_plan("wet", "丰水期(调)", [6, 7, 8], WET_TIERS), wet["id"])
    assert updated["name"] == "丰水期(调)"
    assert updated["months"] == [6, 7, 8]
    assert len(updated["tiers"]) == 3


def test_disabled_plan_skips_overlap_check_but_enabled_reenables_it(conn):
    svc = SeasonService(conn)
    svc.save_plan(_plan("wet", "丰水期", [6, 7, 8], WET_TIERS))
    # 停用方案可以覆盖相同月份
    p = svc.save_plan(_plan("wet2", "丰水期副本", [6, 7], WET_TIERS, enabled=False))
    assert p["enabled"] is False
    # 重新启用时必须报冲突
    with pytest.raises(SeasonConflictError) as ei:
        svc.save_plan(_plan("wet2", "丰水期副本", [6, 7], WET_TIERS, enabled=True), p["id"])
    assert {(c["month"], c["with_code"]) for c in ei.value.conflicts} == {(6, "wet"), (7, "wet")}


def test_duplicate_code_rejected(conn):
    svc = SeasonService(conn)
    svc.save_plan(_plan("wet", "丰水期", [6, 7], WET_TIERS))
    with pytest.raises(ValueError):
        svc.save_plan(_plan("wet", "另一个", [8, 9], WET_TIERS))


# ---------- 账期解析 ----------

def test_resolve_matches_season_plan(conn):
    _save(
        conn,
        _plan("wet", "丰水期", [6, 7, 8, 9, 10], WET_TIERS),
        _plan("dry", "枯水期", [1, 2, 11, 12], DRY_TIERS),
    )
    r = SeasonService(conn).resolve_period(2026, 8)
    assert r["fallback"] is False
    assert r["fallback_reason"] == REASON_MATCHED
    assert r["plan"]["code"] == "wet"
    assert r["plan"]["name"] == "丰水期"
    assert r["tiers"][0]["price"] == 0.45


def test_resolve_no_match_falls_back_with_reason(conn):
    _save(conn, _plan("wet", "丰水期", [6, 7, 8, 9, 10], WET_TIERS))
    r = SeasonService(conn).resolve_period(2026, 4)
    assert r["fallback"] is True
    assert r["fallback_reason"] == REASON_NO_MATCH
    assert r["plan"] is None
    assert r["tiers"] == DEFAULT_TIERS


def test_resolve_no_enabled_plan_reason(conn):
    _save(conn, _plan("wet", "丰水期", [6, 7, 8], WET_TIERS, enabled=False))
    r = SeasonService(conn).resolve_period(2026, 7)
    assert r["fallback"] is True
    assert r["fallback_reason"] == REASON_NO_ENABLED_PLAN
    assert r["tiers"] == DEFAULT_TIERS


def test_resolve_ignores_disabled_plan(conn):
    _save(conn, _plan("wet", "丰水期", [6, 7, 8], WET_TIERS, enabled=False))
    r = SeasonService(conn).resolve_period(2026, 7)
    assert r["fallback"] is True


# ---------- 正式测算走解析结果 ----------

def test_bill_uses_resolved_plan(conn):
    _save(conn, _plan("wet", "丰水期", [6, 7, 8, 9, 10], WET_TIERS))
    with BillingService(conn) as svc:
        out = svc.run_bill(120, False, None, False, 2026, 8, None)
    # 120 * 0.45 = 54.0，走丰水期而非默认(120*0.52=62.4)
    assert out["total"] == 54.0
    assert out["applied"]["fallback"] is False
    assert out["applied"]["plan"]["code"] == "wet"
    assert out["applied"]["month"] == 8


def test_bill_falls_back_for_uncovered_month(conn):
    _save(conn, _plan("wet", "丰水期", [6, 7, 8], WET_TIERS))
    with BillingService(conn) as svc:
        out = svc.run_bill(120, False, None, False, 2026, 3, None)
    assert out["total"] == 62.4
    assert out["applied"]["fallback"] is True
    assert out["applied"]["fallback_reason"] == REASON_NO_MATCH


def test_bill_explicit_plan_code_bypasses_resolution(conn):
    _save(conn, _plan("dry", "枯水期", [1, 12], DRY_TIERS))
    with BillingService(conn) as svc:
        # 7 月本不命中 dry，但显式指定即使用
        out = svc.run_bill(120, False, None, False, 2026, 7, "dry")
    assert out["total"] == 69.6  # 120 * 0.58
    assert out["applied"]["plan"]["code"] == "dry"


def test_bill_unknown_plan_code_raises(conn):
    with BillingService(conn) as svc:
        with pytest.raises(KeyError):
            svc.run_bill(100, False, None, False, 2026, 7, "nope")


# ---------- 只读试算 ----------

def test_trial_is_readonly_returns_summary_and_name(conn):
    _save(conn, _plan("wet", "丰水期", [6, 7, 8], WET_TIERS))
    before = conn.execute("SELECT COUNT(*) c FROM calc_runs").fetchone()["c"]
    r = SeasonService(conn).trial_by_code("wet", 400, False)
    after = conn.execute("SELECT COUNT(*) c FROM calc_runs").fetchone()["c"]
    assert after == before  # 不写运行
    assert r["trial"] is True
    assert r["persisted"] is False
    assert r["plan"]["name"] == "丰水期"
    assert len(r["segment_summary"]) == 3
    # 400: 180*0.45 + 80*0.55 + 140*0.70 = 81+44+98
    assert r["total"] == 223.0
    assert {s["amount"] for s in r["segment_summary"]} == {81.0, 44.0, 98.0}


def test_trial_unknown_code_raises(conn):
    with pytest.raises(KeyError):
        SeasonService(conn).trial_by_code("ghost", 100, False)


def test_trial_peak_applies_factor(conn):
    _save(conn, _plan("wet", "丰水期", [6, 7, 8], WET_TIERS))
    r = SeasonService(conn).trial_by_code("wet", 120, True)
    # 120 * 0.45 * 1.2 = 64.8
    assert r["total"] == 64.8
    assert r["peak_factor"] == 1.2
