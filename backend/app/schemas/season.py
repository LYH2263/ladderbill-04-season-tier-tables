from pydantic import BaseModel, Field


class TierStepIn(BaseModel):
    up_to: float | None = None
    price: float


class SeasonSchemeIn(BaseModel):
    key: str = ""
    name: str
    months: list[int] = Field(default_factory=list)
    tiers: list[TierStepIn] = Field(default_factory=list)
    enabled: bool = True


class TrialRequest(BaseModel):
    kwh: float = Field(ge=0)
    peak: bool = False
