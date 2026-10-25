"""world routes (docs/ARCHITECTURE.md 9.2). Stub router registered by task 1B; task 3C adds the routes."""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["world"])
