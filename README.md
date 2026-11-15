# Customer Loyalty and Engagement Assistant

HCLTech Future Ready AI Engineer Hackathon · Use Case 5.

> **Status:** platform, review, delivery, audit and UI (M4) implemented. Classification,
> policy and generation (M1–M3) are pending; until they land, `PIPELINE_STUBS=true` wires
> scripted placeholders for the ten demo customers (`app/pipeline/stubs.py`).

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev]"
copy .env.example .env          # macOS/Linux: cp .env.example .env
```

Run (two terminals; `make` targets do the same where `make` is installed):

```bash
uvicorn app.main:app --reload --port 8000      # API + docs at http://localhost:8000/docs
streamlit run frontend/streamlit_app.py        # UI at http://localhost:8501
pytest -m "not live" -q                        # tests
```

Demo walkthrough: [docs/demo_script.md](docs/demo_script.md).

## Architecture (request flow)

```
Streamlit UI ──HTTP──> FastAPI routers (no business logic)
                         │
                         ▼
                DraftOrchestrator  (app/pipeline/orchestrator.py)
   profile → features → classification → billing / offers / contact → strategy
        │                                                  │
        │                 NO_CONTACT / ESCALATE ───────────┴──> REFUSED / ESCALATED (no LLM call)
        ▼
   LLM input → generator → slot renderer → guardrails → draft saved (PENDING_REVIEW / BLOCKED)
                         │
                         ▼
   ReviewService  (edit → re-validate; approve bound to content hash; reject with reason)
                         │
                         ▼
   DeliveryGate   (re-checks approval, hash, guardrails, consent) → MockEmailService → outbox/
                         │
   AuditLogger    append-only events, no names/emails/bodies/prompts
```

Every upstream component sits behind a Protocol in `app/pipeline/ports.py` and is wired in
one place, `app/core/container.py`. Without stubs, unbuilt components return
`503 COMPONENT_NOT_READY` naming the owner.

## Main API endpoints (M4)

| Method & path | Purpose |
|---|---|
| `GET /api/v1/health` | Liveness, DB, LLM mode, ruleset version, stub mode |
| `POST /api/v1/drafts` | Full pipeline → draft (201) or REFUSED / ESCALATED (200) |
| `GET /api/v1/drafts` · `GET /api/v1/drafts/{id}` | History list · one draft with evidence, findings, `allowed_actions` |
| `PATCH /api/v1/drafts/{id}` | Reviewer edit → automatic re-validation (invalidates approval) |
| `POST /api/v1/drafts/{id}/validate` | Re-run guardrails |
| `POST /api/v1/drafts/{id}/approve` · `/reject` | Hash-bound approval (WARN needs acknowledgement) · rejection with reason |
| `POST /api/v1/drafts/{id}/deliver` | Mock delivery behind the delivery gate (409 when refused) |
| `GET /api/v1/audit` | Audit events by customer, draft or correlation id |

Errors are always `{"error": {"code", "message", "details"}, "correlation_id"}`; every response
carries an `X-Correlation-ID` header.

## Who owns what

| Member | Area | Folders |
|---|---|---|
| M1 | Data & Classification | `app/data/`, `app/features/`, `app/segmentation/`, `data/synthetic/`, `app/api/routes_customers.py` |
| M2 | Policy Engine | `app/policy/`, `config/policies/{billing,contact,strategy}.yaml`, `app/api/routes_policy.py` |
| M3 | GenAI & Guardrails | `app/generation/`, `app/guardrails/`, `config/templates/`, `config/policies/{tone,disclaimers,blocked_language}.yaml` |
| M4 | Platform, Review & UI | `app/main.py`, `app/core/`, `app/pipeline/`, `app/review/`, `app/delivery/`, `app/audit/`, `frontend/` |

`app/schemas/` is **shared** — changes need approval from all affected owners.

## Git workflow

- Branch from `main`: `feat/m1-feature-builder`, `fix/m3-date-check`, ...
- Small PRs (≤ ~400 lines), at least one reviewer, squash merge.
- Commit style: `feat(policy): add duplicate reminder guard`.
- Never commit `.env`.
