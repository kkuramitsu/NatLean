"""推定・抽出の検証・出力・CLI・キャッシュのオフラインテスト（FakeBackend）"""
import json

import pytest

from natlean import (Argument, CachedModel, FakeBackend, Inference, Interval, NatLean, Prop, report,
                     to_json)
from natlean.cli import main
from natlean.decision import Choice, Noul
from natlean.estimate import Q, estimate_inference, estimate_prop
from natlean.extract import ExtArgument, ExtAttack, ExtInference, ExtProp, build_argument
from natlean.i18n import MESSAGES, resolve_lang, t

TEXT = "人はみな死ぬ。ソクラテスは人である。ゆえに、ソクラテスは死ぬ。"


def socrates(lang="ja"):
    return Argument(
        language=lang,
        props=[Prop("p1", "人はみな死ぬ", "premise"), Prop("p2", "ソクラテスは人である", "premise"),
               Prop("p3", "ソクラテスは死ぬ", "conclusion", paraphrases=["ソクラテスはいずれ死ぬ"])],
        inferences=[Inference("s1", ["p1", "p2"], "p3", "deduction")])


def handler(table):
    """問いの種類（holds / counter / true）→ 答え。Choice には deduction を高く返す"""
    kinds = {}
    for q in Q.values():
        kinds[q["holds_strict"]] = kinds[q["holds_prob"]] = "holds"
        kinds[q["counter"]] = "counter"
        kinds[q["true"]] = "true"

    def h(state, name, q):
        if isinstance(q, Choice):
            return {k: (0.9 if k == "deduction" else 0.1 / (len(q.criteria) - 1)) for k in q.criteria}
        return table.get(kinds.get(q.instructions, name), 0.9)
    return h


# ---------- 推定 ----------

def test_estimate_inference_builds_interval_from_probes():
    fake = FakeBackend(handler({"holds": 0.9, "counter": 0.2}))
    r, probs = estimate_inference(fake, socrates(), socrates().inferences[0], "ja")
    # holds=0.9, 1-counter=0.8, 結論の言い換え 1 件 0.9
    assert (r.lo, r.hi) == (pytest.approx(0.8), pytest.approx(0.9))
    assert max(probs, key=probs.get) == "deduction"


def test_state_contains_only_premises_and_conclusion():
    fake = FakeBackend(handler({"holds": 0.9, "counter": 0.2}))
    arg = socrates()
    estimate_inference(fake, arg, arg.inferences[0], "ja")
    for state, _ in fake.calls:
        assert set(state) == {"premises", "conclusion"}
    assert fake.calls[0][0]["premises"] == ["人はみな死ぬ", "ソクラテスは人である"]


def test_probabilistic_patterns_skip_counterexample_probe():
    fake = FakeBackend(handler({"holds": 0.7}))
    arg = socrates()
    arg.inferences[0].pattern = "induction"
    estimate_inference(fake, arg, arg.inferences[0], "ja")
    names = set(fake.calls[0][1])
    assert "counter" not in names and "holds" in names


def test_estimate_prop_uses_paraphrase_and_negation_complement():
    seen = []

    def h(state, name, q):
        seen.append(state["statement"])
        return 0.2 if "誤り" in state["statement"] else 0.9

    p = Prop("p1", "月は丸い", paraphrases=["月は球形だ"])
    iv, cites, warns = estimate_prop(FakeBackend(h), p, "ja")
    assert cites == [] and warns == []  # 根拠を渡していない
    assert (iv.lo, iv.hi) == (pytest.approx(0.8), pytest.approx(0.9))
    assert len(seen) == 3 and Q["ja"]["negate"].format(s="月は丸い") in seen


def test_check_argument_assume_mode_end_to_end():
    nl = NatLean(FakeBackend(handler({"holds": 0.95, "counter": 0.05})), lang="ja", paraphrases=1)
    res = nl.check_argument(socrates())
    assert res.ok and res.goals == ["p3"]
    assert res.propagation.props["p3"].lo == pytest.approx(0.95)


def test_estimate_mode_estimates_leaf_premises_only():
    fake = FakeBackend(handler({"holds": 1.0, "counter": 0.0}), noul=0.9)
    nl = NatLean(fake, mode="estimate", lang="en")
    arg = socrates()
    nl.check_argument(arg)
    assert arg.props[0].p.est < 1.0 and arg.props[1].p.est < 1.0
    assert arg.props[2].p == Interval(1.0, 1.0, 1.0)  # 結論は推論で決まる


def test_subclass_and_wide_interval_warnings():
    arg = socrates()
    arg.inferences[0].pattern = "subclass"
    state = iter([0.9, 0.3, 0.9])

    def h(st, name, q):
        if isinstance(q, Choice):
            return {k: 1 / len(q.criteria) for k in q.criteria}
        return next(state)

    res = NatLean(FakeBackend(h), lang="en", paraphrases=1).check_argument(arg)
    codes = {w.code for w in res.warnings}
    assert {"subclass", "wide"} <= codes


# ---------- 抽出の検証 ----------

def ext(**kw):
    props = [ExtProp(id="p1", quote="人はみな死ぬ", text="人はみな死ぬ", kind="premise", paraphrases=["a", "b", "c"]),
             ExtProp(id="p2", quote="でたらめ", text="ソクラテスは人である", kind="premise", paraphrases=[]),
             ExtProp(id="p3", quote="ソクラテスは死ぬ", text="ソクラテスは死ぬ", kind="conclusion", paraphrases=[])]
    base = dict(language="ja", props=props,
                inferences=[ExtInference(id="s1", premises=["p1", "p9"], conclusion="p3", pattern="deduction"),
                            ExtInference(id="s2", premises=["p1", "p2"], conclusion="p3", pattern="deduction")],
                attacks=[ExtAttack(kind="undercut", source="p2", target="s9")], ambiguities=[])
    base.update(kw)
    return ExtArgument(**base)


def test_build_argument_validates_quotes_and_references():
    arg = build_argument(ext(), TEXT, max_paraphrases=2)
    codes = [(w.code, w.args["id"]) for w in arg.warnings]
    assert ("quote_not_found", "p2") in codes
    assert sum(1 for c, _ in codes if c == "dangling") == 2  # s1 の p9 と攻撃の s9
    assert [e.id for e in arg.inferences] == ["s2"]
    assert arg.attacks == []
    assert arg.props[0].paraphrases == ["a", "b"]


# ---------- 出力・i18n ----------

@pytest.mark.parametrize("lang", ["ja", "en"])
def test_report_renders_in_both_languages(lang):
    res = NatLean(FakeBackend(handler({"holds": 0.95, "counter": 0.05})), lang=lang).check_argument(socrates())
    text = report(res, lang)
    assert "p3" in text and t("status.proved", lang) in text
    if lang == "en":
        assert "PROVED" in text and "assumed" in text
    else:
        assert "証明済み" in text and "仮定" in text


def test_json_keys_are_language_independent():
    res = NatLean(FakeBackend(handler({"holds": 0.95, "counter": 0.05})), lang="ja").check_argument(socrates())
    a = to_json(res)
    json.dumps(a)  # frozenset などが残っていないこと
    assert set(a) >= {"ok", "goals", "props", "inferences", "warnings", "backend"}


def test_all_messages_have_both_languages():
    for key, msgs in MESSAGES.items():
        assert set(msgs) == {"ja", "en"}, key
        assert msgs["ja"] and msgs["en"], key


def test_all_warn_codes_have_messages():
    import re
    import natlean
    from pathlib import Path
    src = "\n".join(p.read_text(encoding="utf-8") for p in Path(natlean.__file__).parent.rglob("*.py"))
    codes = set(re.findall(r'Warn\("(\w+)"', src))
    assert codes, "警告コードが見つからない"
    for c in codes:
        assert f"warn.{c}" in MESSAGES, c


def test_resolve_lang(monkeypatch):
    monkeypatch.delenv("NATLEAN_LANG", raising=False)
    monkeypatch.setenv("LANG", "ja_JP.UTF-8")
    assert resolve_lang() == "ja" and resolve_lang("en") == "en"
    monkeypatch.setenv("LANG", "C")
    assert resolve_lang() == "en"
    monkeypatch.setenv("NATLEAN_LANG", "ja")
    assert resolve_lang() == "ja"


def test_cli_help_follows_lang(capsys):
    for lang, needle in (("ja", "入力ファイル"), ("en", "input file")):
        with pytest.raises(SystemExit):
            main(["--lang", lang, "--help"])
        assert needle in capsys.readouterr().out


def test_cli_empty_input_is_error(tmp_path, capsys):
    f = tmp_path / "empty.txt"
    f.write_text("  \n")
    assert main([str(f), "--lang", "en"]) == 2
    assert "empty" in capsys.readouterr().err


# ---------- キャッシュ ----------

def test_cache_and_log(tmp_path):
    path = str(tmp_path / "log.jsonl")
    fake = FakeBackend(noul=0.7)
    m = CachedModel(fake, path)
    q = {"q": Noul("この文は真か。")}
    assert m.ask({"statement": "x"}, q) == {"q": 0.7}
    assert m.ask({"statement": "x"}, q) == {"q": 0.7}
    assert len(fake.calls) == 1  # 2回目はキャッシュ
    fake2 = FakeBackend(noul=0.1)
    assert CachedModel(fake2, path).ask({"statement": "x"}, q) == {"q": 0.7}  # ファイルから復元
    assert not fake2.calls
    rec = json.loads(open(path, encoding="utf-8").readline())
    assert rec["version"] == "fake-1" and rec["backend"] == "fake"
