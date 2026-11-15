"""ReasonCodeBuilder: rule trace -> ReasonCode list with fixed-template text.

Owner: M1. Text comes only from reason_codes.yaml; unknown codes fail loudly.
"""

from app.schemas.classification import ReasonCode
from app.schemas.enums import Segment
from app.segmentation.rules import Condition, RuleOutcome


class UnknownReasonCodeError(KeyError):
    pass


class ReasonCodeBuilder:
    def __init__(self, templates: dict[str, str]) -> None:
        self._t = templates

    def one(self, cond: Condition, segment: Segment | None) -> ReasonCode:
        if cond.code not in self._t:
            raise UnknownReasonCodeError(cond.code)
        params = {k: v for k, v in cond.params.items()}
        return ReasonCode(
            code=cond.code, segment=segment, params=params, text=self._t[cond.code].format(**params)
        )

    def build(self, fired: list[RuleOutcome], info: list[Condition]) -> list[ReasonCode]:
        """Codes from supporting conditions of fired rules (first occurrence wins), then info."""
        out: list[ReasonCode] = []
        seen: set[str] = set()
        for rule in fired:
            for cond in rule.supporting:
                if cond.code and cond.code not in seen:
                    seen.add(cond.code)
                    out.append(self.one(cond, rule.segment))
        for cond in info:
            if cond.code and cond.code not in seen:
                seen.add(cond.code)
                out.append(self.one(cond, None))
        return out
