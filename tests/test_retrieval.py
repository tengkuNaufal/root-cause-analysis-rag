from pathlib import Path

from rca.retrieval.chunking import _pieces, split_sections
from rca.retrieval.eval_retrieval import TESTSET, is_relevant, load_testset
from rca.retrieval.translate import is_indonesian, preprocess, strip_details, translate_id_en


def test_testset_covers_every_fault_in_both_languages(sample_catalog):
    catalog = sample_catalog
    items = load_testset(TESTSET)
    assert len(items) == 2 * len(catalog)
    for lang in ("id", "en"):
        assert {i["fault_id"] for i in items if i["lang"] == lang} == set(catalog)
    for i in items:
        assert i["class"] == catalog[i["fault_id"]].fault_class


def test_relevance_groups_are_and_within_or_across():
    assert is_relevant("MTU mismatch blocks DBD", [["mtu", "mismatch"]])
    assert not is_relevant("MTU only", [["mtu", "mismatch"]])
    assert is_relevant("passive-interface eth1", [["mtu"], ["passive"]])


def test_translation_and_detail_stripping():
    q = "Tetangga OSPF r1-r2 di eth1 macet, kenapa? log 2026/11/21 09:12:33 dari 10.0.12.1/30"
    assert is_indonesian(q)
    out = preprocess(q)
    assert "neighbor" in out and "stuck" in out and "why" in out
    assert "10.0.12.1" not in out and "09:12" not in out
    en = "OSPF neighbor stuck in ExStart"
    assert translate_id_en(en) == en
    assert "10.255.0.1" not in strip_details("from 10.255.0.1 at 10:00")


def test_chunking_respects_sections_and_size():
    md = "# T\n\n## A\n" + "Sentence one is here. " * 60 + "\n## B\nShort."
    title, sections = split_sections(md)
    assert title == "T" and [s for s, _ in sections] == ["A", "B"]
    pieces = _pieces(sections[0][1], 300, 60)
    assert len(pieces) > 1 and all(len(p) <= 300 for p in pieces)


def test_corpus_files_exist():
    root = Path(__file__).resolve().parents[1] / "docs" / "corpus"
    assert len(list((root / "base").glob("*.md"))) >= 5
    assert {p.stem for p in (root / "extra").glob("*.md")} >= {"ospf-timers", "ospf-mtu", "bgp-neighbor",
                                                               "prefix-list", "route-map"}
