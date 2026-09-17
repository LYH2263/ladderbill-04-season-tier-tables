import json

from app.db import connect
from app.engines.peak_compare import compare_plain_vs_peak
from app.engines.tier_progressive import calc_bill
from app.repositories import accounts as accounts_repo
from app.repositories import readings as readings_repo
from app.repositories import runs as runs_repo
from app.repositories import season_plans as season_plans_repo
from app.repositories import settings as settings_repo
from app.repositories import tiers as tiers_repo
from app.services.season_service import SeasonService


class BillingService:
    def __init__(self, conn=None):
        self._owns = conn is None
        self._conn = conn or connect()

    def close(self):
        if self._owns:
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
        year: int | None = None,
        month: int | None = None,
        plan_code: str | None = None,
    ):
        pf = settings_repo.peak_factor(self._conn)
        factor = pf if peak else 1.0

        if plan_code is not None:
            # 显式指定档表：直接按方案标识取用，不做月份解析
            plan = season_plans_repo.get_by_code(self._conn, plan_code)
            if plan is None:
                raise KeyError(plan_code)
            tiers = [{"up_to": t["up_to"], "price": t["price"]} for t in plan["tiers"]]
            applied = {
                "fallback": False,
                "fallback_reason": "matched",
                "plan": {
                    "id": plan["id"],
                    "code": plan["code"],
                    "name": plan["name"],
                    "months": plan["months"],
                },
                "year": year,
                "month": month,
            }
            year_resolved, month_resolved = year, month
        else:
            # 未显式指定：正式测算必须走账期解析结果，无命中回退全局默认 tiers
            resolved = SeasonService(self._conn).resolve_period(year, month)
            year_resolved, month_resolved = resolved["year"], resolved["month"]
            tiers = resolved["tiers"]
            applied = {
                "fallback": resolved["fallback"],
                "fallback_reason": resolved["fallback_reason"],
                "plan": resolved["plan"],
                "year": year_resolved,
                "month": month_resolved,
            }

        result = calc_bill(kwh, tiers, factor)
        run_id = None
        if persist:
            run_id = runs_repo.insert(
                self._conn,
                "bill",
                {
                    "kwh": kwh,
                    "peak": peak,
                    "account_id": account_id,
                    "year": year_resolved,
                    "month": month_resolved,
                    "plan_code": plan_code,
                    "applied": applied,
                },
                result,
                account_id,
            )
        return {"run_id": run_id, "applied": applied, **result}

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
