"""Deterministic policy engine. MUST NOT import app.generation.

Owner: M2.

Modules:
    billing.py    decide_billing        -> BillingDecision    (FR-06)
    offers.py     decide_offers         -> OfferDecision      (FR-05)
    contact.py    check_contact         -> ContactDecision    (FR-07, pre-generation)
    strategy.py   select_strategy, apply_contact -> StrategyDecision (FR-03)
    llm_input.py  build_llm_input       -> LLMInput           (FR-04 input)
    config.py     typed loaders for config/policies/{billing,contact,strategy}.yaml
"""
