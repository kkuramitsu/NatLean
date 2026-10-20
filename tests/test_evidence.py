"""根拠文書の検索・推定・出どころの追跡のオフラインテスト"""
import json

import pytest

from natlean import (Argument, EvidenceIndex, FakeBackend, Inference, Interval, NatLean, Prop, propagate,
                     report, to_json)
from natlean.cli import main
from natlean.decision import Choice, Noul
from natlean.estimate import Q, estimate_prop
from natlean.evidence import split_passages
from natlean.graph import Cite

DOC_A = ("ソクラテスは古代ギリシャの哲学者である。紀元前399年に毒杯をあおいで死んだ。\n\n"
         "プラトンはソクラテスの弟子である。アカデメイアを創設した。")
DOC_B = "Tokyo is the capital of Japan. It has about 14 million residents."


# ---------- 検索 ----------

def test_split_passages_by_paragraph_and_length():
    assert len(split_passages(DOC_A)) == 2
    long = "あ。" * 400
    parts = split_passages(long, max_chars=100)
    assert all(len(p) <= 100 for p in parts) and "".join(parts) == long
    assert all(len(p) <= 600 for p in split_passages("x" * 1500))  # 句点が無くても切る


def test_search_finds_relevant_passage_in_both_languages():
    ix = EvidenceIndex({"a.txt": DOC_A, "b.txt": DOC_B})
    top = ix.search("ソクラテスは毒杯で死んだ")[0][0]
    assert (top.source, top.index) == ("a.txt", 1)
    assert ix.search("Tokyo is the capital of Japan")[0][0].source == "b.txt"
    assert ix.search("月はチーズでできている") == []


def test_from_paths_reads_files_and_directories(tmp_path):
    (tmp_path / "a.txt").write_text(DOC_A, encoding="utf-8")
    (tmp_path / "skip.pdf").write_text("x")
    sub = tmp_path / "docs"
    sub.mkdir()
    (sub / "b.md").write_text(DOC_B, encoding="utf-8")
    ix = EvidenceIndex.from_paths([str(tmp_path / "a.txt"), str(sub)])
    assert {p.source for p in ix.passages} == {"a.txt", "b.md"}


# ---------- 推定 ----------

def evidence_handler(truth):
    """truth: passage に含まれる語 → その passage のもとでの真の確率。無ければ無関係"""
    def h(state, name, q):
        passage = state.get("evidence", "")
        hit = next((v for k, v in truth.items() if k in passage), None)
        if isinstance(q, Choice):
            if hit is None:
                return {"supports": 0.05, "contradicts": 0.05, "unrelated": 0.9}
            return {"supports": 0.9, "contradicts": 0.05, "unrelated": 0.05} if hit >= 0.5 else \
                   {"supports": 0.05, "contradicts": 0.9, "unrelated": 0.05}
        true = 0.5 if hit is None else hit
        return 1 - true if "誤り" in state["statement"] else true
    return h


def test_estimate_prop_with_evidence_records_cites():
    ix = EvidenceIndex({"a.txt": DOC_A})
    fake = FakeBackend(evidence_handler({"毒杯": 0.97}))
    iv, cites, warns = estimate_prop(fake, Prop("p1", "ソクラテスは毒杯で死んだ"), "ja", ix)
    assert iv.lo == pytest.approx(0.97) and iv.hi == pytest.approx(0.97)
    assert [(c.source, c.index, c.relation) for c in cites] == [("a.txt", 1, "supports")]
    assert warns == []
    # state には命題と passage だけを入れる
    assert all(set(state) <= {"statement", "evidence"} for state, _ in fake.calls)


def test_estimate_prop_falls_back_to_prior_when_no_relevant_passage():
    ix = EvidenceIndex({"a.txt": DOC_A})
    fake = FakeBackend(evidence_handler({}), noul=0.8)
    iv, cites, warns = estimate_prop(fake, Prop("p1", "月はチーズでできている"), "ja", ix)
    assert cites == [] and [w.code for w in warns] == ["no_evidence"]
    assert 0 <= iv.lo <= iv.hi <= 1


def test_unrelated_passage_is_not_used():
    ix = EvidenceIndex({"a.txt": DOC_A})
    fake = FakeBackend(evidence_handler({"プラトン": 0.99}))  # 検索には掛かるが、判定は無関係
    _, cites, warns = estimate_prop(fake, Prop("p1", "ソクラテスは哲学者だ"), "ja", ix)
    assert all(c.relation in ("supports", "contradicts") for c in cites)


def test_conflicting_evidence_widens_interval_and_warns():
    ix = EvidenceIndex({"a.txt": "ソクラテスは毒杯で死んだ。", "b.txt": "ソクラテスは老衰で死んだ。ソクラテスは毒杯を飲まなかった。"})
    fake = FakeBackend(evidence_handler({"毒杯で": 0.95, "老衰": 0.05}))
    iv, cites, warns = estimate_prop(fake, Prop("p1", "ソクラテスは毒杯で死んだ"), "ja", ix)
    assert {c.relation for c in cites} == {"supports", "contradicts"}
    assert iv.width > 0.5 and any(w.code == "evidence_conflict" for w in warns)


def test_check_argument_uses_evidence_in_estimate_mode_and_reports_cites():
    ix = EvidenceIndex({"a.txt": DOC_A})
    arg = Argument(language="ja",
                   props=[Prop("p1", "ソクラテスは毒杯で死んだ"), Prop("p2", "毒杯で死んだ者は死んだ", "conclusion")],
                   inferences=[Inference("s1", ["p1"], "p2", "deduction")])

    def h(state, name, q):
        if "evidence" in state or "statement" in state:
            return evidence_handler({"毒杯": 0.97})(state, name, q)
        if isinstance(q, Choice):
            return {"deduction": 1.0}
        return 0.97 if q.instructions != Q["ja"]["counter"] else 0.03

    res = NatLean(FakeBackend(h), mode="estimate", evidence=ix, lang="en", paraphrases=0).check_argument(arg)
    assert arg.props[0].p.est == pytest.approx(0.97) and arg.props[0].cites
    assert "a.txt#1 supports" in report(res, "en") and "a.txt#1 裏付け" in report(res, "ja")
    out = to_json(res)
    json.dumps(out)
    assert out["props"][0]["cites"][0]["source"] == "a.txt"


# ---------- 出どころの追跡（二重計上） ----------

def P(i, p=1.0, sources=()):
    prop = Prop(i, i, p=Interval.point(p))
    prop.cites = [Cite(s, 1, "supports", p) for s in sources]
    return prop


def E(i, prem, concl):
    return Inference(i, prem, concl, "deduction", Interval.point(1.0))


def test_supports_from_the_same_source_are_not_independent():
    arg = Argument(props=[P("a", 0.5, ["x.txt"]), P("b", 0.5, ["x.txt"]), P("c")],
                   inferences=[E("s1", ["a"], "c"), E("s2", ["b"], "c")])
    res = propagate(arg)
    assert res.props["c"].est == pytest.approx(0.5)  # noisy-OR の 0.75 ではなく max
    w = [w for w in res.warnings if w.code == "shared_source"]
    assert len(w) == 1 and w[0].args["source"] == "x.txt"
    assert not any(w.code == "double_count" for w in res.warnings)  # 葉や推論は重なっていない


def test_supports_from_different_sources_are_independent():
    arg = Argument(props=[P("a", 0.5, ["x.txt"]), P("b", 0.5, ["y.txt"]), P("c")],
                   inferences=[E("s1", ["a"], "c"), E("s2", ["b"], "c")])
    res = propagate(arg)
    assert res.props["c"].est == pytest.approx(0.75)
    assert not res.warnings


def test_sources_propagate_through_inference_chain():
    arg = Argument(props=[P("a", 0.5, ["x.txt"]), P("b", 0.5, ["x.txt"]), P("m"), P("c")],
                   inferences=[E("s1", ["a"], "m"), E("s2", ["m"], "c"), E("s3", ["b"], "c")])
    res = propagate(arg)
    assert res.props["m"].sources == {"x.txt"}
    assert any(w.code == "shared_source" for w in res.warnings)


# ---------- CLI ----------

def test_cli_evidence_defaults_to_estimate_mode(tmp_path, monkeypatch):
    doc = tmp_path / "ev.txt"
    doc.write_text(DOC_A, encoding="utf-8")
    inp = tmp_path / "in.txt"
    inp.write_text("x")
    seen = {}

    class Stub:
        def __init__(self, decision, **kw):
            seen.update(kw)

        def check(self, text):
            raise SystemExit(0)

    monkeypatch.setattr("natlean.cli.NatLean", Stub)
    monkeypatch.setattr("natlean.cli.make_backend", lambda *a, **k: FakeBackend())
    with pytest.raises(SystemExit):
        main([str(inp), "--evidence", str(doc)])
    assert seen["mode"] == "estimate" and seen["evidence"].passages
    with pytest.raises(SystemExit):
        main([str(inp)])
    assert seen["mode"] == "assume" and seen["evidence"] is None
