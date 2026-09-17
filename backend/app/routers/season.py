from fastapi import APIRouter, HTTPException

from app.schemas.season import SeasonSchemeIn, TrialRequest
from app.services.billing_service import BillingService
from app.services.season_service import (
    SeasonConflictError,
    SeasonNotFoundError,
    SeasonValidationError,
)

router = APIRouter(tags=["season"])


def _conflict_http(exc: SeasonConflictError) -> HTTPException:
    return HTTPException(409, {"message": str(exc), "conflicts": exc.conflicts})


@router.get("/season-schemes")
def list_season_schemes():
    with BillingService() as svc:
        return {"items": svc.list_season_schemes()}


@router.get("/season-schemes/resolve")
def resolve_season(period: str | None = None):
    with BillingService() as svc:
        try:
            return svc.resolve_season(period)
        except SeasonValidationError as e:
            raise HTTPException(400, str(e))


@router.post("/season-schemes", status_code=201)
def create_season_scheme(body: SeasonSchemeIn):
    with BillingService() as svc:
        try:
            return svc.create_season_scheme(body.model_dump())
        except SeasonConflictError as e:
            raise _conflict_http(e)
        except SeasonValidationError as e:
            raise HTTPException(400, str(e))


@router.get("/season-schemes/{key}")
def get_season_scheme(key: str):
    with BillingService() as svc:
        row = svc.get_season_scheme(key)
        if not row:
            raise HTTPException(404, "scheme not found")
        return row


@router.put("/season-schemes/{key}")
def update_season_scheme(key: str, body: SeasonSchemeIn):
    with BillingService() as svc:
        try:
            return svc.update_season_scheme(key, body.model_dump())
        except SeasonNotFoundError:
            raise HTTPException(404, "scheme not found")
        except SeasonConflictError as e:
            raise _conflict_http(e)
        except SeasonValidationError as e:
            raise HTTPException(400, str(e))


@router.delete("/season-schemes/{key}", status_code=204)
def delete_season_scheme(key: str):
    with BillingService() as svc:
        try:
            svc.delete_season_scheme(key)
        except SeasonNotFoundError:
            raise HTTPException(404, "scheme not found")


@router.post("/season-schemes/{key}/trial")
def trial_season_scheme(key: str, body: TrialRequest):
    with BillingService() as svc:
        try:
            return svc.trial_season_scheme(key, body.kwh, body.peak)
        except SeasonNotFoundError:
            raise HTTPException(404, "scheme not found")
