"""Wiring of concrete implementations (Dependency Inversion).

Owner: M4. The ONLY place concrete classes are chosen. Tests build a Container with overrides;
production uses `build_container(get_settings())`.

Real M1/M2/M3 components are wired in `_real_components` as they land. Until then the API
starts normally, /health works, and pipeline endpoints return 503 COMPONENT_NOT_READY unless
PIPELINE_STUBS=true (scripted placeholders, see app/pipeline/stubs.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.audit.logger import AuditLogger
from app.core.errors import ComponentNotReadyError
from app.core.policy_loader import ruleset_version
from app.data.db import init_db, make_engine, make_session_factory
from app.delivery.gate import DeliveryGate
from app.delivery.mock_email import MockEmailService
from app.pipeline.orchestrator import DraftOrchestrator, PipelineComponents
from app.pipeline.ports import CommunicationRecorderPort
from app.review.service import ReviewService
from config.settings import Settings


@dataclass
class Container:
    settings: Settings
    engine: Engine
    sessions: sessionmaker[Session]
    audit: AuditLogger
    components: PipelineComponents
    comms: CommunicationRecorderPort
    orchestrator: DraftOrchestrator
    review: ReviewService
    delivery: DeliveryGate
    ruleset_version: str

    def db_status(self) -> str:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return "ok"
        except Exception:  # noqa: BLE001 - health check must never raise
            return "error"


class _NotReady:
    """Placeholder for a component whose owner has not delivered it yet."""

    def __init__(self, name: str, owner: str) -> None:
        self._name, self._owner = name, owner

    def __getattr__(self, _attr: str) -> Any:
        def _raise(*_a: Any, **_k: Any) -> Any:
            raise ComponentNotReadyError(
                f"{self._name} ({self._owner}) is not implemented yet. "
                "Set PIPELINE_STUBS=true to use the scripted demo placeholders.",
                details={"component": self._name, "owner": self._owner},
            )

        return _raise


def _real_components() -> tuple[PipelineComponents, CommunicationRecorderPort]:
    """Wire real implementations here as each owner delivers them (replace _NotReady)."""
    comms = _NotReady("CommunicationRecorder", "M1")
    components = PipelineComponents(
        profiles=_NotReady("ProfileAssembler", "M1"),
        features=_NotReady("FeatureBuilder", "M1"),
        segmenter=_NotReady("SegmentationEngine", "M1"),
        classifications=_NotReady("ClassificationRecorder", "M1"),
        billing=_NotReady("BillingPolicyEngine", "M2"),
        offers=_NotReady("OfferEligibilityEngine", "M2"),
        contact=_NotReady("ContactPolicyGate", "M2"),
        strategy=_NotReady("StrategySelector", "M2"),
        llm_input=_NotReady("LLMInputBuilder", "M2"),
        generator=_NotReady("MessageGenerator", "M3"),
        renderer=_NotReady("SlotRenderer", "M3"),
        guardrails=_NotReady("GuardrailRunner", "M3"),
    )
    return components, comms  # type: ignore[return-value]


def build_container(
    settings: Settings,
    *,
    components: PipelineComponents | None = None,
    comms: CommunicationRecorderPort | None = None,
) -> Container:
    engine = make_engine(settings.database_url)
    init_db(engine)
    sessions = make_session_factory(engine)
    audit = AuditLogger(sessions)

    if components is None:
        if settings.pipeline_stubs:
            from app.pipeline.stubs import build_stub_components

            components, comms = build_stub_components(
                adversarial_provider=settings.llm_provider == "fake_adversarial"
            )
        else:
            components, comms = _real_components()
    if comms is None:
        comms = _NotReady("CommunicationRecorder", "M1")  # type: ignore[assignment]

    return Container(
        settings=settings,
        engine=engine,
        sessions=sessions,
        audit=audit,
        components=components,
        comms=comms,
        orchestrator=DraftOrchestrator(components, sessions, audit),
        review=ReviewService(sessions, components.guardrails, audit),
        delivery=DeliveryGate(
            sessions,
            guardrails=components.guardrails,
            profiles=components.profiles,
            contact=components.contact,
            mailer=MockEmailService(settings.outbox_dir),
            comms=comms,
            audit=audit,
        ),
        ruleset_version=ruleset_version(settings.config_dir),
    )
