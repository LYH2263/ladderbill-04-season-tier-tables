"""Season tier tables: payload validation, month-exclusivity, period resolution.

Pure service module (no FastAPI imports) so it can be reused by BillingService
and smoke-tested without the web stack.
"""

import re

from app.engines.tier_progressive import calc_bill
from app.repositories import season_schemes as schemes_repo
from app.repositories import settings as settings_repo
from app.repositories import tiers as tiers_repo

# Fallback reason enum, surfaced in resolve/bill responses.
REASON_NO_PERIOD = "no_period"
REASON_NO_MATCHING_SCHEME = "no_matching_scheme"
FALLBACK_REASONS = (REASON_NO_PERIOD, REASON_NO_MATCHING_SCHEME)

_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_PERIOD_RE = re.compile(r"^(\d{4})-(\d{1,2})$")


class SeasonValidationError(ValueError):
    """Bad scheme payload or bad period format."""


class SeasonConflictError(Exception):
    """Enabled schemes' month sets must be pairwise disjoint."""

    def __init__(self, conflicts: list[dict]):
        self.conflicts = conflicts
        months = ",".join(str(c["month"]) for c in conflicts)
        keys = ",".join(sorted({c["scheme_key"] for c in conflicts}))
        super().__init__(f"生效月份冲突：月份[{months}] 已被启用方案[{keys}]占用")


class SeasonNotFoundError(Exception):
    pass


def _validate(data: dict) -> dict:
    key = str(data.get("key") or "").strip()
    if not _KEY_RE.match(key):
        raise SeasonValidationError("方案标识须以字母或数字开头，可含字母、数字、-、_，最长64字符")
    name = str(data.get("name") or "").strip()
    if not name:
        raise SeasonValidationError("方案名称不能为空")
    try:
        months = sorted({int(m) for m in data.get("months") or []})
    except (TypeError, ValueError):
        raise SeasonValidationError("生效月份须为 1-12 的整数")
    if not months:
        raise SeasonValidationError("生效月份不能为空")
    if any(m < 1 or m > 12 for m in months):
        raise SeasonValidationError("生效月份须在 1-12 之间")
    raw_tiers = data.get("tiers") or []
    if not raw_tiers:
        raise SeasonValidationError("阶梯序列不能为空")
    tiers = []
    prev = 0.0
    for i, t in enumerate(raw_tiers):
        try:
            price = float(t.get("price"))
        except (TypeError, ValueError):
            raise SeasonValidationError(f"第{i + 1}档单价无效")
        if price < 0:
            raise SeasonValidationError(f"第{i + 1}档单价不能为负")
        up = t.get("up_to")
        if up is None:
            if i != len(raw_tiers) - 1:
                raise SeasonValidationError("仅最后一档可不限上限")
        else:
            try:
                up = float(up)
            except (TypeError, ValueError):
                raise SeasonValidationError(f"第{i + 1}档上限无效")
            if up <= prev:
                raise SeasonValidationError("阶梯上限必须严格递增")
            prev = up
        tiers.append({"up_to": up, "price": price})
    return {
        "key": key,
        "name": name,
        "months": months,
        "tiers": tiers,
        "enabled": bool(data.get("enabled", True)),
    }


def _check_conflicts(conn, norm: dict):
    if not norm["enabled"]:
        return
    conflicts = schemes_repo.find_month_conflicts(conn, norm["months"], exclude_key=norm["key"])
    if conflicts:
        raise SeasonConflictError(conflicts)


def list_schemes(conn) -> list[dict]:
    return schemes_repo.list_all(conn)


def get_scheme(conn, key: str) -> dict | None:
    return schemes_repo.get_by_key(conn, key)


def create_scheme(conn, data: dict) -> dict:
    norm = _validate(data)
    if schemes_repo.get_by_key(conn, norm["key"]):
        raise SeasonValidationError(f"方案标识 {norm['key']} 已存在")
    _check_conflicts(conn, norm)
    return schemes_repo.create(conn, **norm)


def update_scheme(conn, key: str, data: dict) -> dict:
    if not schemes_repo.get_by_key(conn, key):
        raise SeasonNotFoundError(key)
    norm = _validate({**data, "key": key})
    _check_conflicts(conn, norm)
    return schemes_repo.update(conn, **norm)


def delete_scheme(conn, key: str):
    if not schemes_repo.delete(conn, key):
        raise SeasonNotFoundError(key)


def parse_period(period: str) -> tuple[int, int]:
    m = _PERIOD_RE.match(str(period or "").strip())
    if not m:
        raise SeasonValidationError("账期格式应为 YYYY-MM")
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        raise SeasonValidationError("账期月份须在 1-12 之间")
    return year, month


def _resolution(*, source, fallback, reason, scheme=None, tiers=None, period=None, month=None):
    return {
        "period": period,
        "month": month,
        "source": source,
        "fallback": fallback,
        "reason": reason,
        "scheme_key": scheme["key"] if scheme else None,
        "scheme_name": scheme["name"] if scheme else None,
        "tiers": tiers if tiers is not None else (scheme["tiers"] if scheme else []),
    }


def resolve_tiers(conn, period: str | None = None, scheme_key: str | None = None) -> dict:
    """Which tier ladder applies for a billing period.

    Explicit scheme_key wins; otherwise the enabled scheme covering the period
    month; otherwise the global default tiers with fallback reason set.
    """
    if scheme_key:
        scheme = schemes_repo.get_by_key(conn, scheme_key)
        if not scheme:
            raise SeasonNotFoundError(scheme_key)
        month = parse_period(period)[1] if period else None
        return _resolution(source="explicit", fallback=False, reason=None, scheme=scheme, period=period, month=month)
    if period:
        _, month = parse_period(period)
        scheme = schemes_repo.find_covering(conn, month)
        if scheme:
            return _resolution(source="season", fallback=False, reason=None, scheme=scheme, period=period, month=month)
        return _resolution(
            source="default",
            fallback=True,
            reason=REASON_NO_MATCHING_SCHEME,
            tiers=tiers_repo.as_calc_rows(conn),
            period=period,
            month=month,
        )
    return _resolution(
        source="default",
        fallback=True,
        reason=REASON_NO_PERIOD,
        tiers=tiers_repo.as_calc_rows(conn),
    )


def trial(conn, key: str, kwh: float, peak: bool = False) -> dict:
    """Read-only preview against a scheme's ladder; never writes calc_runs."""
    scheme = schemes_repo.get_by_key(conn, key)
    if not scheme:
        raise SeasonNotFoundError(key)
    pf = settings_repo.peak_factor(conn)
    factor = pf if peak else 1.0
    result = calc_bill(kwh, scheme["tiers"], factor)
    return {"scheme_key": scheme["key"], "scheme_name": scheme["name"], **result}
