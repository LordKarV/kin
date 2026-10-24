from app.graph.ontology import lookup
from tests.graph_fixtures import graph  # noqa: F401


def test_relation_how_phrases_are_listener_relative(graph):
    a = graph.by_slug["p_arjun"].id
    assert graph.how(a, graph.by_slug["p_ravi_mama"].id) == "Mom's younger brother"
    assert graph.how(a, graph.by_slug["p_ravi_periyappa"].id) == "Dad's elder brother"
    assert graph.how(a, graph.by_slug["p_kamala"].id) == "Mom's mom"
    assert graph.how(a, graph.by_slug["p_lakshmi"].id) == "Mom's younger brother's wife"
    assert graph.how(a, graph.by_slug["p_karthik"].id) == "Mom's younger brother's son"
    assert graph.how(a, graph.by_slug["p_saroja"].id) == "Mom's mom's younger sister"


def test_roles(graph):
    a = graph.by_slug["p_arjun"].id
    assert graph.role(a, graph.by_slug["p_ravi_mama"].id) == "uncle"
    assert graph.role(a, graph.by_slug["p_lakshmi"].id) == "aunt"
    assert graph.role(a, graph.by_slug["p_karthik"].id) == "cousin"
    assert graph.role(a, graph.by_slug["p_divya"].id) == "elder sister"
    assert graph.role(a, graph.by_slug["p_kamala"].id) == "grandmother"
    assert graph.role(a, graph.by_slug["p_saroja"].id) == "grand-aunt"
    assert graph.role(a, graph.by_slug["p_priya"].id) == "mom"


def test_render_person_includes_name_role_address_term_and_how(graph):
    a = graph.by_slug["p_arjun"].id
    r = graph.render(a, graph.by_slug["p_ravi_mama"].id)
    assert r == "your uncle Ravi mama (Mom's younger brother)"
    assert graph.render(a, graph.by_slug["p_kamala"].id) == "your grandmother Kamala paatti (Mom's mom)"
    assert graph.render(a, a) == "you (Arjun)"


def test_resolve_kin_term_from_listener_and_speaker_perspectives(graph):
    arjun, kamala = graph.by_slug["p_arjun"].id, graph.by_slug["p_kamala"].id
    assert graph.resolve_kin_term(lookup("mama"), arjun) == {graph.by_slug["p_ravi_mama"].id}
    assert graph.resolve_kin_term(lookup("periyappa"), arjun) == {graph.by_slug["p_ravi_periyappa"].id}
    assert graph.resolve_kin_term(lookup("magan"), kamala) == {graph.by_slug["p_ravi_mama"].id}
    assert graph.resolve_kin_term(lookup("thangai"), kamala) == {graph.by_slug["p_saroja"].id}
    assert graph.resolve_kin_term(lookup("marumagal"), kamala) == {graph.by_slug["p_lakshmi"].id}
    assert graph.resolve_kin_term(lookup("maapillai"), kamala) == {graph.by_slug["p_senthil"].id}
    assert graph.resolve_kin_term(lookup("akka"), arjun) == {graph.by_slug["p_divya"].id}


def test_family_address_term_overrides_ontology(graph):
    # Arjun's family calls Vishnu "anna" (edge lang_term) although he is a cross-cousin
    arjun = graph.by_slug["p_arjun"].id
    assert graph.address_term(arjun, graph.by_slug["p_divya"].id) == "akka"


def test_distance_prefers_speakers_own_son(graph):
    kamala = graph.by_slug["p_kamala"].id
    assert graph.distance(kamala, graph.by_slug["p_ravi_mama"].id) == 1
    assert graph.distance(kamala, graph.by_slug["p_ravi_periyappa"].id) >= 3
