import json

from app.db import connect
from app.engines.peak_compare import compare_plain_vs_peak
from app.engines.tier_progressive import calc_bill
from app.repositories import accounts as accounts_repo
from app.repositories import readings as readings_repo
from app.repositories import runs as runs_repo
from app.repositories import settings as settings_repo
from app.repositories import tiers as tiers_repo
from app.services import season_service


class BillingService:
    def __init__(self):
        self._conn = connect()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def list_accounts(self):
        return accounts_repo.list_all(self._conn)

    def get_account(self, account_id: int):
        return accounts_repo.get(self._conn, account_id)

    def list_tiers(self):
        return tiers_repo.list_ordered(self._conn)

    def list_readings(self):
        return readings_repo.list_all(self._conn)

    def readings_for_account(self, account_id: int):
        return readings_repo.for_account(self._conn, account_id)

    def settings_map(self):
        return settings_repo.get_map(self._conn)

    def run_bill(
        self,
        kwh: float,
        peak: bool,
        account_id: int | None,
        persist: bool,
        period: str | None = None,
        scheme_key: str | None = None,
    ):
        # 未显式指定档表时按账期解析季节方案，未命中回退全局默认 tiers
        resolution = season_service.resolve_tiers(self._conn, period, scheme_key)
        pf = settings_repo.peak_factor(self._conn)
        factor = pf if peak else 1.0
        result = calc_bill(kwh, resolution["tiers"], factor)
        result["tier_source"] = {
            k: resolution[k]
            for k in ("source", "fallback", "reason", "scheme_key", "scheme_name", "period", "month")
        }
        run_id = None
        if persist:
            run_id = runs_repo.insert(
                self._conn,
                "bill",
                {"kwh": kwh, "peak": peak, "account_id": account_id, "period": period, "scheme_key": scheme_key},
                result,
                account_id,
            )
        return {"run_id": run_id, **result}

    def run_compare(self, kwh: float, persist: bool):
        tiers = tiers_repo.as_calc_rows(self._conn)
        pf = settings_repo.peak_factor(self._conn)
        result = compare_plain_vs_peak(kwh, tiers, pf)
        run_id = None
        if persist:
            run_id = runs_repo.insert(self._conn, "compare", {"kwh": kwh}, result, None)
        return {"run_id": run_id, **result}

    def list_history(self, limit: int = 50):
        return runs_repo.list_recent(self._conn, limit)

    def list_season_schemes(self):
        return season_service.list_schemes(self._conn)

    def get_season_scheme(self, key: str):
        return season_service.get_scheme(self._conn, key)

    def create_season_scheme(self, data: dict):
        return season_service.create_scheme(self._conn, data)

    def update_season_scheme(self, key: str, data: dict):
        return season_service.update_scheme(self._conn, key, data)

    def delete_season_scheme(self, key: str):
        return season_service.delete_scheme(self._conn, key)

    def resolve_season(self, period: str | None = None, scheme_key: str | None = None):
        return season_service.resolve_tiers(self._conn, period, scheme_key)

    def trial_season_scheme(self, key: str, kwh: float, peak: bool = False):
        return season_service.trial(self._conn, key, kwh, peak)

    def get_run(self, run_id: int):
        return runs_repo.get(self._conn, run_id)

    def dashboard_stats(self):
        accounts = accounts_repo.list_all(self._conn)
        readings = readings_repo.list_all(self._conn)
        clean = [a for a in accounts if "种子" not in a.get("name", "")]
        dirty = [a for a in accounts if "种子" in a.get("name", "")]
        return {
            "account_count": len(accounts),
            "reading_count": len(readings),
            "clean_accounts": len(clean),
            "dirty_accounts": len(dirty),
            "recent_runs": len(runs_repo.list_recent(self._conn, 5)),
        }
