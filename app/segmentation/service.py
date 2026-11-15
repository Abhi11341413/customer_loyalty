"""ClassificationService: profile -> features -> classification (-> persisted).

Owner: M1. This is the Profile->Classification boundary the orchestrator (M4) calls.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.data.repositories.classification_repo import SqlClassificationWriter
from app.data.repositories.customer_repo import SqlCustomerReader
from app.features.builder import FeatureBuilder
from app.features.profile import ProfileAssembler
from app.schemas.classification import ClassificationResult
from app.schemas.customer import CustomerFeatures, CustomerProfile
from app.segmentation.config import SegmentationConfig, default_config
from app.segmentation.engine import SegmentationEngine


@dataclass(frozen=True)
class ClassificationOutput:
    profile: CustomerProfile
    features: CustomerFeatures
    result: ClassificationResult


class ClassificationService:
    def __init__(
        self,
        assembler: ProfileAssembler,
        builder: FeatureBuilder,
        engine: SegmentationEngine,
        writer: SqlClassificationWriter | None = None,
    ) -> None:
        self.assembler, self.builder, self.engine, self.writer = assembler, builder, engine, writer

    @classmethod
    def from_session(
        cls, session: Session, config: SegmentationConfig | None = None
    ) -> "ClassificationService":
        cfg = config or default_config()
        return cls(
            ProfileAssembler(SqlCustomerReader(session)),
            FeatureBuilder(cfg.features),
            SegmentationEngine(cfg),
            SqlClassificationWriter(session),
        )

    def profile_and_features(
        self, customer_id: str, as_of: date
    ) -> tuple[CustomerProfile, CustomerFeatures]:
        profile = self.assembler.assemble(customer_id, as_of)
        return profile, self.builder.build(profile)

    def classify(self, customer_id: str, as_of: date, persist: bool = True) -> ClassificationOutput:
        profile, features = self.profile_and_features(customer_id, as_of)
        result = self.engine.classify(features)
        if persist and self.writer is not None:
            cid = self.writer.save(result, features)
            result = result.model_copy(update={"classification_id": cid})
        return ClassificationOutput(profile, features, result)
