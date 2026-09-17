import pytest
from fastapi.testclient import TestClient

from app.db import connect
from app.main import app

SUMMER = {
    "key": "summer",
    "name": "夏季方案",
    "months": [6, 7, 8],
    "tiers": [{"up_to": 200, "price": 0.5}, {"up_to": None, "price": 0.9}],
    "enabled": True,
}
WINTER = {
    "key": "winter",
    "name": "冬季方案",
    "months": [12, 1, 2],
    "tiers": [{"up_to": 100, "price": 0.4}, {"up_to": None, "price": 0.7}],
    "enabled": True,
}


def _purge_schemes():
    conn = connect()
    conn.execute("DELETE FROM season_schemes")
    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_schemes(client):
    _purge_schemes()
    yield
    _purge_schemes()


def _create(client, payload):
    return client.post("/api/season-schemes", json=payload)


def test_create_and_get_scheme(client):
    r = _create(client, SUMMER)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["key"] == "summer"
    assert body["months"] == [6, 7, 8]
    assert body["enabled"] is True
    got = client.get("/api/season-schemes/summer")
    assert got.status_code == 200
    assert got.json()["name"] == "夏季方案"
    listed = client.get("/api/season-schemes").json()["items"]
    assert [s["key"] for s in listed] == ["summer"]


def test_conflict_reports_months_and_scheme_keys(client):
    assert _create(client, SUMMER).status_code == 201
    clash = {**WINTER, "key": "winter2", "months": [8, 12]}
    r = _create(client, clash)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["conflicts"] == [{"month": 8, "scheme_key": "summer", "scheme_name": "夏季方案"}]
    assert "8" in detail["message"] and "summer" in detail["message"]


def test_disabled_scheme_does_not_conflict(client):
    assert _create(client, SUMMER).status_code == 201
    off = {**WINTER, "months": [6, 12], "enabled": False}
    assert _create(client, off).status_code == 201


def test_update_excludes_self_but_checks_others(client):
    assert _create(client, SUMMER).status_code == 201
    assert _create(client, WINTER).status_code == 201
    ok = client.put("/api/season-schemes/summer", json={**SUMMER, "name": "夏季方案v2"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["name"] == "夏季方案v2"
    bad = client.put("/api/season-schemes/summer", json={**SUMMER, "months": [1, 6]})
    assert bad.status_code == 409
    assert bad.json()["detail"]["conflicts"][0]["scheme_key"] == "winter"


def test_delete_scheme(client):
    assert _create(client, SUMMER).status_code == 201
    assert client.delete("/api/season-schemes/summer").status_code == 204
    assert client.get("/api/season-schemes/summer").status_code == 404
    assert client.delete("/api/season-schemes/summer").status_code == 404


def test_validation_errors(client):
    assert _create(client, {**SUMMER, "months": [6, 13]}).status_code == 400
    assert _create(client, {**SUMMER, "months": []}).status_code == 400
    assert _create(client, {**SUMMER, "tiers": []}).status_code == 400
    descending = {"tiers": [{"up_to": 300, "price": 0.5}, {"up_to": 100, "price": 0.6}]}
    assert _create(client, {**SUMMER, "tiers": descending}).status_code == 400
    open_mid = {"tiers": [{"up_to": None, "price": 0.5}, {"up_to": 100, "price": 0.6}]}
    assert _create(client, {**SUMMER, "tiers": open_mid}).status_code == 400
    assert _create(client, {**SUMMER, "key": "带 空格"}).status_code == 400
    dup = _create(client, SUMMER)
    assert dup.status_code == 201
    assert _create(client, SUMMER).status_code == 400


def test_resolve_hit_and_fallback(client):
    _create(client, SUMMER)
    hit = client.get("/api/season-schemes/resolve", params={"period": "2026-07"}).json()
    assert hit["fallback"] is False
    assert hit["reason"] is None
    assert hit["scheme_key"] == "summer"
    assert hit["scheme_name"] == "夏季方案"
    assert hit["month"] == 7
    assert hit["tiers"] == SUMMER["tiers"]

    miss = client.get("/api/season-schemes/resolve", params={"period": "2026-03"}).json()
    assert miss["fallback"] is True
    assert miss["reason"] == "no_matching_scheme"
    assert miss["scheme_key"] is None
    assert miss["tiers"]  # 回退到全局默认 tiers

    none_given = client.get("/api/season-schemes/resolve").json()
    assert none_given["fallback"] is True
    assert none_given["reason"] == "no_period"

    bad = client.get("/api/season-schemes/resolve", params={"period": "2026-13"})
    assert bad.status_code == 400


def test_bill_uses_resolved_scheme(client):
    _create(client, SUMMER)  # 200 度内 0.5，超出 0.9
    r = client.post("/api/bill", json={"kwh": 300, "period": "2026-07", "persist": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tier_source"]["scheme_key"] == "summer"
    assert body["tier_source"]["scheme_name"] == "夏季方案"
    assert body["tier_source"]["fallback"] is False
    assert body["total"] == 190.0  # 200×0.5 + 100×0.9
    assert body["run_id"]


def test_bill_fallback_marks_reason(client):
    _create(client, SUMMER)
    r = client.post("/api/bill", json={"kwh": 100, "period": "2026-03"})
    src = r.json()["tier_source"]
    assert src["fallback"] is True
    assert src["reason"] == "no_matching_scheme"
    assert src["scheme_key"] is None
    # 全局默认档表 180 内 0.52
    assert r.json()["total"] == 52.0

    r2 = client.post("/api/bill", json={"kwh": 100})
    assert r2.json()["tier_source"]["reason"] == "no_period"


def test_bill_explicit_scheme_key(client):
    _create(client, SUMMER)
    r = client.post("/api/bill", json={"kwh": 100, "period": "2026-03", "scheme_key": "summer"})
    src = r.json()["tier_source"]
    assert src["source"] == "explicit"
    assert src["scheme_key"] == "summer"
    assert r.json()["total"] == 50.0
    missing = client.post("/api/bill", json={"kwh": 100, "scheme_key": "nope"})
    assert missing.status_code == 404
    bad_period = client.post("/api/bill", json={"kwh": 100, "period": "07/2026"})
    assert bad_period.status_code == 400


def test_trial_is_readonly(client):
    _create(client, SUMMER)
    before = len(client.get("/api/history").json()["items"])
    r = client.post("/api/season-schemes/summer/trial", json={"kwh": 300})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scheme_name"] == "夏季方案"
    assert body["total"] == 190.0  # 200×0.5 + 100×0.9
    assert len(body["segments"]) == 2
    assert "run_id" not in body
    after = len(client.get("/api/history").json()["items"])
    assert after == before
    assert client.post("/api/season-schemes/nope/trial", json={"kwh": 1}).status_code == 404
