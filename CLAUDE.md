# KIN — working agreements for Claude Code

- Read KIN_BUILD_PLAN.md (the plan) before any task. Work only on the phase named in the request.
- Never invent API endpoints, parameter names, or model IDs. If an external detail is unknown, say so and check docs; mark it VERIFY in docs/DECISIONS.md.
- All LLM calls go through backend/app/llm.py (OpenAI-compatible client; base URL and model from env). No direct SDK calls elsewhere.
- All external calls have a timeout and a fallback path per the plan §3.
- Structured outputs are validated with Pydantic; failures are logged, never silently swallowed.
- Every stage in the audio pipeline records latency into the utterance's `latencies` field.
- Keep the eval runnable at all times: `cd backend && python -m eval.run_eval` must not break.
- Tests: pytest, fast, no network (mock providers). Run `cd backend && pytest` before claiming a phase is complete.
- One-line entries in docs/DECISIONS.md for every non-obvious choice.
- Do not add dependencies without noting why in DECISIONS.md.
- Privacy rules in the plan §9 are hard constraints.

## Layout
- `backend/` FastAPI app (`app/`), tests (`tests/`), eval harness (`eval/`). Run from `backend/`.
- `frontend/` Vite + React single page (call, graph, glossary, fade tabs).
- `scripts/` seed and data tooling. `docs/` decisions, demo script, Devpost draft.

## Commands
- `cd backend && source .venv/bin/activate && uvicorn app.main:app --reload`
- `cd backend && pytest -q`
- `cd backend && python -m app.smoke` (needs MODEL_API_KEY)
- `cd backend && python -m eval.run_eval` (needs MODEL_API_KEY; `--mock` runs offline)
- `cd frontend && npm run dev`
