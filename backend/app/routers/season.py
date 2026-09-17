from fastapi import APIRouter, HTTPException

from app.schemas.season import SeasonPlanIn, SeasonTrialRequest
from app.services.season_service import SeasonConflictError, SeasonService

router = APIRouter(tags=["season"])


@router.get("/season-plans")
def list_plans():
    with SeasonService() as svc:
        return {"items": svc.list_plans()}


@router.post("/season-plans")
def create_plan(body: SeasonPlanIn):
    with SeasonService() as svc:
        try:
            plan = svc.save_plan(body.model_dump())
        except SeasonConflictError as e:
            raise HTTPException(409, {"message": str(e), "conflicts": e.conflicts})
        except ValueError as e:
            raise HTTPException(400, str(e))
        return plan


@router.put("/season-plans/{plan_id}")
def update_plan(plan_id: int, body: SeasonPlanIn):
    with SeasonService() as svc:
        try:
            plan = svc.save_plan(body.model_dump(), plan_id)
        except SeasonConflictError as e:
            raise HTTPException(409, {"message": str(e), "conflicts": e.conflicts})
        except ValueError as e:
            raise HTTPException(400, str(e))
        return plan


@router.delete("/season-plans/{plan_id}")
def delete_plan(plan_id: int):
    with SeasonService() as svc:
        if not svc.delete_plan(plan_id):
            raise HTTPException(404, "方案不存在")
        return {"ok": True}


@router.get("/season-plans/resolve")
def resolve_period(year: int | None = None, month: int | None = None):
    """按账期年月解析应用哪套方案；无命中回退全局默认 tiers 并标记 fallback。"""
    with SeasonService() as svc:
        try:
            return svc.resolve_period(year, month)
        except ValueError as e:
            raise HTTPException(400, str(e))


@router.post("/season-plans/{code}/trial")
def trial_plan(code: str, body: SeasonTrialRequest):
    """按方案标识的只读试算：返回方案名与分段摘要，不写运行记录。"""
    with SeasonService() as svc:
        try:
            return svc.trial_by_code(code, body.kwh, body.peak)
        except KeyError:
            raise HTTPException(404, f"方案不存在：{code}")
