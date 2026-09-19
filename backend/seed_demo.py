"""Seed a demo research group with real CodeCraft models (mock removed).

- Deletes any legacy provider='mock' rows.
- Creates CodeCraft models (per-model api_key empty = use .env CODECRAFT_API_KEY).
- Run: .\.venv\Scripts\python seed_demo.py
"""
from app.database import Base, SessionLocal, engine
from app import models

Base.metadata.create_all(bind=engine)
db = SessionLocal()

# 1. Remove legacy mocks.
deleted = db.query(models.LLMModel).filter_by(provider="mock").delete(synchronize_session=False)
db.commit()
if deleted:
    print(f"Removed {deleted} legacy mock model(s).")

ROLE_PROMPTS = {
    "Gemma (Lead)": (
        "codecraft", "gemma-2-2b",
        "You are the lead researcher. Analyze carefully, develop hypotheses, explain reasoning, identify uncertainty explicitly.",
    ),
    "Muse Spark (Skeptic)": (
        "codecraft", "muse-spark-1.1",
        "You are the skeptical researcher. Critically examine previous responses for unsupported assumptions, logical errors, missing evidence.",
    ),
    "GPT Sol (Analyst)": (
        "codecraft", "gpt-5.6-sol",
        "You are the mathematical analyst. Check reasoning rigorously, derive equations where useful.",
    ),
    "Claude Opus (Synthesizer)": (
        "codecraft", "claude-opus-5",
        "You are the synthesizer. Integrate strongest arguments, resolve contradictions, state what is established vs unresolved.",
    ),
}

group = db.query(models.Group).filter_by(name="Physics Research").first()
if not group:
    group = models.Group(name="Physics Research", description="Demo group: dark energy, QM, cosmology")
    db.add(group)
    db.commit()
    db.refresh(group)

for i, (name, (provider, model_name, prompt)) in enumerate(ROLE_PROMPTS.items()):
    m = db.query(models.LLMModel).filter_by(name=name).first()
    if not m:
        m = models.LLMModel(
            name=name, provider=provider, model_name=model_name,
            system_prompt=prompt, temperature=0.7, max_output_tokens=1024,
            api_key="", base_url="",
        )
        db.add(m)
        db.commit()
        db.refresh(m)
    link = (
        db.query(models.GroupModel)
        .filter_by(group_id=group.id, model_id=m.id)
        .first()
    )
    if not link:
        db.add(models.GroupModel(group_id=group.id, model_id=m.id, turn_order=i, is_enabled=True))
        db.commit()

print(f"Seeded group id={group.id} with {len(ROLE_PROMPTS)} CodeCraft models (no mocks).")
db.close()
