"""Persist classification runs to classification_results (history + audit evidence).

Owner: M1.
"""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.data import models as m
from app.schemas.classification import ClassificationResult
from app.schemas.customer import CustomerFeatures


class SqlClassificationWriter:
    def __init__(self, session: Session) -> None:
        self._s = session

    def save(self, result: ClassificationResult, features: CustomerFeatures) -> str:
        """Insert one row and return the new classification_id. Features hold no PII."""
        cid = str(uuid.uuid4())
        self._s.add(
            m.ClassificationResultRow(
                classification_id=cid,
                customer_id=result.customer_id,
                as_of_date=result.as_of_date.isoformat(),
                segments=json.dumps([s.value for s in result.segments]),
                primary_segment=result.primary_segment.value,
                reason_codes=json.dumps([r.model_dump(mode="json") for r in result.reason_codes]),
                confidence=result.confidence,
                features_snapshot=features.model_dump_json(),
                ruleset_version=result.ruleset_version,
                shadow_model_label=result.shadow.label if result.shadow else None,
                created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
        )
        self._s.commit()
        return cid
