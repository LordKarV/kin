import pytest
from app.db.session import init_db, reset_engine, session_scope
from app.db.seed import seed_demo_family
from app.graph.kinship import FamilyGraph


@pytest.fixture
def graph() -> FamilyGraph:
    reset_engine(); init_db()
    with session_scope() as s:
        fam = seed_demo_family(s)
        return FamilyGraph.from_session(s, fam.id)
