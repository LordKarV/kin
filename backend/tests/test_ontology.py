from app.graph.ontology import KIN_TERMS, lookup, normalize_term

def test_lookup_mama_is_mothers_brother_and_affinal_variants():
    t = lookup("mama")
    assert t is not None
    assert "mother.brother" in t.patterns
    assert "father.sister.husband" in t.patterns

def test_lookup_handles_tamil_script_and_spelling_variants():
    assert lookup("மாமா").term == "mama"
    assert lookup("maama").term == "mama"
    assert lookup("Periyappa").term == "periyappa"
    assert lookup("chiththappa").term == "chithappa"

def test_periyappa_is_fathers_elder_brother():
    assert "father.elder_brother" in lookup("periyappa").patterns

def test_endearments_are_not_relations():
    k = lookup("kanna")
    assert k.kind == "endearment" and not k.patterns

def test_ontology_has_enough_coverage():
    assert len([t for t in KIN_TERMS if t.kind == "kin"]) >= 20

def test_normalize_strips_case_and_long_vowels():
    assert normalize_term("Maamaa") == "mama"
