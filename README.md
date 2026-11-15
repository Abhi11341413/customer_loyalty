# Customer Loyalty and Engagement Assistant

HCLTech Future Ready AI Engineer Hackathon · Use Case 5.

> **Status:** project skeleton only.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev]"
copy .env.example .env          # macOS/Linux: cp .env.example .env
```

Run (once implemented): `make run-api`, `make run-ui`, `make test`.

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
