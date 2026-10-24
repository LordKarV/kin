"""Phase 0 smoke test: one structured completion from Muse Spark. `python -m app.smoke`"""
import json

from pydantic import BaseModel

from .llm import get_llm


class Greeting(BaseModel):
    language: str
    greeting: str
    romanized: str


if __name__ == "__main__":
    llm = get_llm()
    out = llm.structured(Greeting, system="Answer in the requested JSON schema only.", user="Give a warm Tamil greeting a grandchild says to their grandmother.")
    print(json.dumps(out.model_dump(), ensure_ascii=False, indent=2))
    print(f"model={llm.model} latency_ms={llm.last_latency_ms:.0f}")
