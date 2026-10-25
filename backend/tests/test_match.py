import random
import statistics
import time

from app.world.match import AliasIndex, fold, script_of, skel


def ids(hits, kind=None):
    return [h.ids for h in hits if kind is None or h.kind == kind]


def test_fold_maps_back_to_original_indexes():
    f, idx = fold("Lín!")
    assert f == "lin "
    assert idx == [0, 1, 2, 3]
    f, idx = fold("Lín")              # decomposed accent is dropped
    assert f == "lin" and idx == [0, 1, 3]
    assert fold("ﬁ")[0] == "fi"            # NFKC expansion, both chars point at index 0
    assert fold("ﬁ")[1] == [0, 0]


def test_script_of_and_skel():
    assert script_of("林") == "han" and script_of("さ") == "hiragana" and script_of("ล") == "thai"
    assert script_of("Ｌ") == "latin" and script_of("ை") == "tamil"
    assert skel("Lynn") == "lin" and skel("Linh") == "linh" and skel("Philippa") == "filipa"


def test_single_han_char_with_cue():
    hits = AliasIndex([("林", "person", 1)]).scan("我和林去攀岩了")
    assert [(h.start, h.end, h.ids) for h in hits] == [(2, 3, (1,))]


def test_single_han_char_inside_word_is_rejected():
    assert AliasIndex([("林", "person", 1)]).scan("林檎を食べた") == []


def test_single_han_char_with_honorific():
    hits = AliasIndex([("林", "person", 1)]).scan("林さんが来た")
    assert ids(hits) == [(1,)] and (hits[0].start, hits[0].end) == (0, 1)


def test_thai_unspaced():
    hits = AliasIndex([("ลิน", "person", 1)]).scan("ลินไปปีนเขา")
    assert [(h.start, h.end, h.ids) for h in hits] == [(0, 3, (1,))]


def test_single_char_thai_never():
    assert AliasIndex([("ล", "person", 1)]).scan("ล ไป") == []


def test_latin_variants_hit_same_id():
    idx = AliasIndex([("Lín", "person", 17)])
    for text, exact in (("I saw Lín", True), ("I saw Lin today", True), ("I saw Lynn today", False)):
        hits = idx.scan(text)
        assert ids(hits) == [(17,)], text
        assert hits[0].exact is exact and hits[0].surface in ("Lín", "Lin", "Lynn")


def test_linh_is_not_lin():
    assert AliasIndex([("Lin", "person", 1)]).scan("Linh called") == []


def test_maya_is_not_may_for_english_speaker():
    idx = AliasIndex([("May", "person", 1)])
    assert idx.scan("Maya called", speaker_lang="en") == []
    assert ids(idx.scan("May's dog", speaker_lang="en")) == [(1,)]


def test_tamil_case_suffix():
    idx = AliasIndex([("மதுரை", "thing", 5)])
    hits = idx.scan("நான் மதுரைக்கு போனேன்", speaker_lang="ta")
    assert [(h.kind, h.ids, h.surface) for h in hits] == [("thing", (5,), "மதுரை")]
    assert idx.scan("நான் மதுரைக்கு போனேன்") == []    # no speaker language, no suffixes


def test_unknown_speaker_lang_means_no_suffixes():
    assert AliasIndex([("May", "person", 1)]).scan("Mays", speaker_lang="xx") == []


def test_longest_form_wins():
    hits = AliasIndex([("林", "person", 1), ("林小美", "person", 2)]).scan("我和林小美去")
    assert [(h.start, h.end, h.ids) for h in hits] == [(2, 5, (2,))]


def test_offsets_survive_nfkc_expansion():
    hits = AliasIndex([("Lin", "person", 1)]).scan("ﬁ Lin")
    assert (hits[0].start, hits[0].end, hits[0].surface) == (2, 5, "Lin")
    hits = AliasIndex([("Lin", "person", 1)]).scan("ＬＩＮ说")
    assert (hits[0].start, hits[0].end) == (0, 3)


def test_keyword_fact_forms_in_unspaced_text():
    idx = AliasIndex([("林", "person", 1), ("攀岩", "fact", 9)])
    hits = idx.scan("我和林去攀岩了")
    assert [(h.kind, h.ids, h.start, h.end) for h in hits] == [("person", (1,), 2, 3), ("fact", (9,), 4, 6)]


def test_one_hit_per_kind_per_span():
    hits = AliasIndex([("Lin", "person", 1), ("Lín", "person", 2), ("Lin", "group", 3)]).scan("Lin")
    assert sorted((h.kind, h.ids) for h in hits) == [("group", (3,)), ("person", (1, 2))]


def test_code_mixed_latin_name_in_chinese():
    assert ids(AliasIndex([("Lin", "person", 1)]).scan("我跟Lin去")) == [(1,)]


def test_scan_speed_5000_forms():
    rnd = random.Random(0)
    letters = "abcdefghijklmnoprstuvwz"
    han = "林王李张刘陈杨黄赵周吴徐孙马朱胡郭何高罗"
    forms = [("".join(rnd.choice(letters) for _ in range(rnd.randint(3, 9))), "person", i) for i in range(2500)]
    forms += [("".join(rnd.choice(han) for _ in range(rnd.randint(2, 3))), "person", 2500 + i) for i in range(2500)]
    idx = AliasIndex(forms)
    line = (" ".join(f for f, _, _ in forms[:30]) + " 我和林去攀岩了 " * 10)[:300]
    runs = []
    for _ in range(50):
        t = time.perf_counter()
        idx.scan(line, speaker_lang="en")
        runs.append(time.perf_counter() - t)
    assert statistics.median(runs) < 0.002


def test_single_han_char_needs_both_boundaries_without_cue():
    # Deliberate recall cost of rejecting 林檎 at text start (stricter than ARCHITECTURE 3.2's wording).
    idx = AliasIndex([("林", "person", 1)])
    assert idx.scan("我想林。") == []
    assert idx.scan("林去了") == []
    assert ids(idx.scan("Lin 林 说")) == [(1,)]


def test_skeleton_alternatives_survive_an_exact_hit():
    idx = AliasIndex([("Lin", "person", 1), ("Lynn", "person", 2)])
    for text, exact_id, skel_id in (("Lynn came", 2, 1), ("Lin came", 1, 2)):
        hits = idx.scan(text)
        assert [(h.start, h.end, h.ids, h.exact) for h in hits] == [
            (0, len(text.split()[0]), (exact_id,), True), (0, len(text.split()[0]), (skel_id,), False)], text


def test_tamil_name_ending_in_pulli_takes_case_suffix():
    idx = AliasIndex([("அர்ஜுன்", "person", 1)])
    text = "அர்ஜுனுக்கு சொன்னேன்"
    hits = idx.scan(text, speaker_lang="ta")
    assert [(h.start, h.end, h.ids) for h in hits] == [(0, len("அர்ஜுன"), (1,))]
    assert idx.scan(text) == []                              # no speaker language, no suffixes
    assert idx.scan("அர்ஜுன சொன்னேன்", speaker_lang="ta") == []   # pulli-less stem alone is not the name
    assert ids(idx.scan("அர்ஜுன் சொன்னான்", speaker_lang="ta")) == [(1,)]


def test_span_keeps_trailing_decomposed_accent():
    hits = AliasIndex([("José", "person", 1)]).scan("José vino")
    assert (hits[0].start, hits[0].end, hits[0].surface) == (0, 5, "José")


def test_roman_suffixes_only_for_non_latin_speaker_table():
    idx = AliasIndex([("Minji", "person", 1)])
    assert ids(idx.scan("Minjiga wasseo", speaker_lang="ko")) == [(1,)]
    assert idx.scan("Minjiga wasseo", speaker_lang="en") == []


def test_single_han_char_inside_compound_is_rejected_even_before_a_cue():
    # 柏林/森林/小林 are one word; the right cue (的, 都, さん) must not rescue the 林 inside them.
    lin, li, zhang = (AliasIndex([(f, "person", 1)]) for f in ("林", "李", "张"))
    for idx, text in ((lin, "柏林的冬天很冷"), (lin, "森林都烧了"), (lin, "小林さんが来た"), (li, "我的行李也丢了"), (zhang, "你紧张吗")):
        assert idx.scan(text) == [], text
    for text in ("我和林去攀岩了", "林也喜欢攀岩", "我跟林说", "昨日は林さんが来た"):   # kana on the left is a boundary
        assert ids(lin.scan(text)) == [(1,)], text
    # a Han char that ends a common word is a boundary (昨天, 然后, 所以, 见了, 他说)
    for text in ("他说林也来", "然后林说", "昨天林也来了", "所以林也去了", "今天林都没来", "我见了林也很高兴", "我见了林。"):
        assert ids(lin.scan(text)) == [(1,)], text
    assert lin.scan("传说林中") == []       # word end on the left still needs a cue or boundary on the right
    assert lin.scan("他想林也来") == []      # recall cost: any other Han char on the left


def test_capitalized_name_does_not_match_a_lowercase_word_in_cased_text():
    idx = AliasIndex([("Will", "person", 1), ("May", "person", 2), ("An", "person", 3), ("Grace", "person", 4)])
    for text in ("I will call you in may", "I had an apple", "We said grace"):
        assert idx.scan(text) == [], text
    assert ids(idx.scan("I saw May and Will")) == [(2,), (1,)]
    assert ids(idx.scan("i saw may today")) == [(2,)]          # all-lowercase STT: case carries no signal
    assert ids(idx.scan("Will you come")) == [(1,)]           # ceiling: sentence-initial word still matches


def test_case_rule_decides_per_id_not_per_shared_terminal():
    # Amma and amma fold to one terminal; only the person with a lowercase form is case-blind, in either order.
    for forms in ([("Amma", "person", 1), ("amma", "person", 2)], [("amma", "person", 2), ("Amma", "person", 1)]):
        assert ids(AliasIndex(forms).scan("I told amma")) == [(2,)], forms
        assert sorted(ids(AliasIndex(forms).scan("I told Amma"))[0]) == [1, 2], forms
    # the skeleton trie shares terminals across spellings too (Lynn and lin both skeleton to lin)
    assert ids(AliasIndex([("Lynn", "person", 1), ("lin", "person", 2)]).scan("I told lin")) == [(2,)]


def test_case_rule_is_for_people_only():
    # dishes, groups and concept keys are common words that STT writes lowercase
    idx = AliasIndex([("Dosa", "thing", 1), ("Climbing club", "group", 2), ("Climbing", "fact", 3)])
    assert sorted(h.kind for h in idx.scan("We had dosa after climbing club")) == ["group", "thing"]
    assert ids(idx.scan("We went climbing", "en")) == [(3,)]


def test_katakana_form_inside_a_katakana_word_is_rejected():
    idx = AliasIndex([("リン", "person", 1)])
    assert idx.scan("リンゴを食べた") == [] and idx.scan("キリンを見た") == [] and idx.scan("リンーー") == []
    assert ids(idx.scan("リンさんが来た")) == [(1,)] and ids(idx.scan("昨日リンと会った")) == [(1,)]


def test_thai_form_ending_before_a_vowel_sign_is_rejected():
    idx = AliasIndex([("ลิน", "person", 1)])
    assert idx.scan("ไปคลินิก") == [] and idx.scan("ลินา") == []
    assert idx.scan("เลิน") == [] and idx.scan("ไปเลินไป") == []   # leading vowel belongs to the first consonant
    assert ids(idx.scan("ลินไปปีนเขา")) == [(1,)]
