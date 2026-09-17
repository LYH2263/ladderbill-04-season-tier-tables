from pydantic import BaseModel, Field, field_validator, model_validator


class SeasonTierIn(BaseModel):
    up_to: float | None = None
    price: float = Field(gt=0)


class SeasonPlanIn(BaseModel):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=80)
    months: list[int] = Field(min_length=1)
    enabled: bool = True
    tiers: list[SeasonTierIn] = Field(min_length=1)

    @field_validator("months")
    @classmethod
    def _validate_months(cls, v: list[int]) -> list[int]:
        bad = [m for m in v if not 1 <= m <= 12]
        if bad:
            raise ValueError("月份必须在 1-12 之间")
        if len(set(v)) != len(v):
            raise ValueError("生效月份不可重复")
        return v

    @model_validator(mode="after")
    def _validate_tiers(self):
        prev = 0.0
        for i, t in enumerate(self.tiers):
            last = i == len(self.tiers) - 1
            if t.up_to is None:
                if not last:
                    raise ValueError("只有最后一档可以不设上限")
            else:
                if t.up_to <= prev:
                    raise ValueError("阶梯上限必须严格递增且为正")
                prev = t.up_to
        if self.tiers[-1].up_to is not None:
            raise ValueError("最后一档必须不设上限（开放区间），以构成完整阶梯")
        return self


class SeasonTrialRequest(BaseModel):
    kwh: float = Field(ge=0)
    peak: bool = False
