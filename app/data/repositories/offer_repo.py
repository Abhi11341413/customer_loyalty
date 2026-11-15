"""OfferReader: read-only campaign/offer access for M2's OfferEligibilityEngine.

Owner: M1 (implementation) — interface agreed with M2.
Returns ALL offers with their campaign; eligibility filtering is M2's job.
"""

import json
from datetime import date
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data import models as m
from app.data.repositories import _convert as cv
from app.schemas.campaign import Campaign, CampaignOffer, OfferRedemption


class OfferReader(Protocol):
    def campaigns(self) -> list[Campaign]: ...
    def offers(self) -> list[CampaignOffer]: ...
    def redemptions_for(self, customer_id: str, as_of: date) -> list[OfferRedemption]: ...


class SqlOfferReader:
    def __init__(self, session: Session) -> None:
        self._s = session

    def campaigns(self) -> list[Campaign]:
        rows = self._s.scalars(select(m.CampaignRow).order_by(m.CampaignRow.campaign_id))
        return [
            Campaign(
                campaign_id=r.campaign_id,
                name=r.name,
                status=r.status,
                start_date=cv.d(r.start_date),
                end_date=cv.d(r.end_date),
                approved_by=r.approved_by,
            )
            for r in rows
        ]

    def offers(self) -> list[CampaignOffer]:
        plan_map: dict[str, list[str]] = {}
        for e in self._s.scalars(select(m.OfferPlanEligibility)):
            plan_map.setdefault(e.offer_id, []).append(e.plan_id)
        rows = self._s.scalars(select(m.CampaignOfferRow).order_by(m.CampaignOfferRow.offer_id))
        return [
            CampaignOffer(
                offer_id=r.offer_id,
                campaign_id=r.campaign_id,
                offer_type=r.offer_type,
                title=r.title,
                value_type=r.value_type,
                value=r.value,
                terms_summary=r.terms_summary,
                valid_from=cv.d(r.valid_from),
                valid_to=cv.d(r.valid_to),
                channel=r.channel,
                eligible_segments=json.loads(r.eligible_segments),
                min_tenure_months=r.min_tenure_months,
                requires_no_overdue=bool(r.requires_no_overdue),
                max_per_customer=r.max_per_customer,
                total_cap=r.total_cap,
                total_redeemed=r.total_redeemed,
                eligible_plan_ids=sorted(plan_map.get(r.offer_id, [])),
            )
            for r in rows
        ]

    def redemptions_for(self, customer_id: str, as_of: date) -> list[OfferRedemption]:
        stmt = (
            select(m.OfferRedemptionRow)
            .where(m.OfferRedemptionRow.customer_id == customer_id)
            .where(m.OfferRedemptionRow.redeemed_at < (as_of.isoformat() + "T99"))
        )
        return [
            OfferRedemption(
                redemption_id=r.redemption_id,
                offer_id=r.offer_id,
                customer_id=r.customer_id,
                redeemed_at=cv.ts(r.redeemed_at),
            )
            for r in self._s.scalars(stmt)
        ]
