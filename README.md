# KIN

A family-specific interpreter for calls between diaspora grandchildren and their grandparents.
Translates live, grounds every translation on *this family's* people, places and foods, remembers across calls,
and fades its own translation as the grandchild learns the language.

Plan: [KIN_BUILD_PLAN.md](KIN_BUILD_PLAN.md). Decisions: [docs/DECISIONS.md](docs/DECISIONS.md).

## Run

```bash
cp .env.example .env            # fill in MODEL_API_KEY, DEEPGRAM_API_KEY, ELEVENLABS_API_KEY
cd backend && python3.12 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
python -m app.smoke             # one structured completion from Muse Spark
uvicorn app.main:app --reload   # http://localhost:8000/health
```

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Tests: `cd backend && pytest -q`. Eval: `cd backend && python -m eval.run_eval`.
