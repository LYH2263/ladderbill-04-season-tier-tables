from datetime import datetime

from app.db import connect
from app.engines.tier_progressive import calc_bill
from app.repositories import season_plans as plans_repo
from app.repositories import settings as settings_repo
from app.repositories import tiers as tiers_repo

# 回退原因枚举
REASON_MATCHED = "matched"
REASON_NO_ENABLED_PLAN = "no_enabled_plan"
REASON_NO_MATCH = "no_match"


class SeasonConflictError(Exception):
    """保存方案时与其它启用方案的生效月份相交。"""

    def __init__(self, conflicts: list[dict]):
        self.conflicts = conflicts
        months = "、".join(f"{c['month']}月(与 {c['with_code']} 冲突)" for c in conflicts)
        super().__init__(f"生效月份与其它启用方案冲突：{months}")


class SeasonService:
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

    # ---------- 方案维护 ----------

    def list_plans(self) -> list[dict]:
        return plans_repo.list_all(self._conn)

    def save_plan(self, payload: dict, plan_id: int | None = None) -> dict:
        if payload["enabled"]:
            conflicts = self._month_conflicts(payload["months"], payload["code"], plan_id)
            if conflicts:
                raise SeasonConflictError(conflicts)

        existing = plans_repo.get_by_code(self._conn, payload["code"])
        if existing and existing["id"] != plan_id:
            raise ValueError(f"方案标识已存在：{payload['code']}")

        new_id = plans_repo.upsert(self._conn, payload, plan_id)
        return plans_repo.get_by_id(self._conn, new_id)

    def delete_plan(self, plan_id: int) -> bool:
        if not plans_repo.get_by_id(self._conn, plan_id):
            return False
        plans_repo.delete(self._conn, plan_id)
        return True

    def _month_conflicts(self, months: list[int], code: str, plan_id: int | None) -> list[dict]:
        """返回与其它启用方案相交的月份及冲突方案标识。"""
        conflicts: list[dict] = []
        for other in plans_repo.list_all(self._conn, enabled_only=True):
            if other["id"] == plan_id:
                continue
            for m in months:
                if m in other["months"]:
                    conflicts.append({"month": m, "with_code": other["code"], "with_name": other["name"]})
        return conflicts

    # ---------- 账期解析 ----------

    def resolve_period(self, year: int | None, month: int | None) -> dict:
        """按账期年月解析应使用的档表；无命中回退全局默认 tiers。"""
        if month is None:
            month = datetime.now().month
        if year is None:
            year = datetime.now().year
        if not 1 <= month <= 12:
            raise ValueError("月份必须在 1-12 之间")

        enabled = plans_repo.list_all(self._conn, enabled_only=True)
        plan = next((p for p in enabled if month in p["months"]), None)

        if plan is not None:
            return {
                "year": year,
                "month": month,
                "fallback": False,
                "fallback_reason": REASON_MATCHED,
                "plan": self._plan_brief(plan),
                "tiers": self._calc_rows(plan),
            }

        if not enabled:
            reason = REASON_NO_ENABLED_PLAN
        else:
            reason = REASON_NO_MATCH
        return {
            "year": year,
            "month": month,
            "fallback": True,
            "fallback_reason": reason,
            "plan": None,
            "tiers": tiers_repo.as_calc_rows(self._conn),
        }

    # ---------- 只读试算 ----------

    def trial_by_code(self, code: str, kwh: float, peak: bool) -> dict:
        plan = plans_repo.get_by_code(self._conn, code)
        if plan is None:
            raise KeyError(code)
        pf = settings_repo.peak_factor(self._conn)
        result = calc_bill(kwh, self._calc_rows(plan), pf if peak else 1.0)
        return {
            "plan": self._plan_brief(plan),
            "trial": True,
            "persisted": False,
            "segment_summary": self._segment_summary(plan, result),
            **result,
        }

    @staticmethod
    def _calc_rows(plan: dict) -> list[dict]:
        return [{"up_to": t["up_to"], "price": t["price"]} for t in plan["tiers"]]

    @staticmethod
    def _plan_brief(plan: dict) -> dict:
        return {"id": plan["id"], "code": plan["code"], "name": plan["name"], "months": plan["months"]}

    @staticmethod
    def _segment_summary(plan: dict, result: dict) -> list[dict]:
        return [
            {
                "from_kwh": s["from_kwh"],
                "to_kwh": s["to_kwh"],
                "qty": s["qty"],
                "price": s["price"],
                "amount": s["amount"],
            }
            for s in result["segments"]
        ]
