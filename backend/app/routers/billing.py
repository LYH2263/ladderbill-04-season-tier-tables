from fastapi import APIRouter, HTTPException

from app.schemas.billing import BillRequest, CompareRequest
from app.services.billing_service import BillingService
from app.services.season_service import SeasonNotFoundError, SeasonValidationError

router = APIRouter(tags=["billing"])


@router.post("/bill")
def post_bill(body: BillRequest):
    with BillingService() as svc:
        try:
            return svc.run_bill(body.kwh, body.peak, body.account_id, body.persist, body.period, body.scheme_key)
        except SeasonNotFoundError as e:
            raise HTTPException(404, f"scheme not found: {e}")
        except SeasonValidationError as e:
            raise HTTPException(400, str(e))


@router.post("/compare")
def post_compare(body: CompareRequest):
    with BillingService() as svc:
        return svc.run_compare(body.kwh, body.persist)
