"""実 API を呼ぶテスト（課金あり）

    pytest -m "not api"     # 除外
    pytest -m jev           # Jev を使うものだけ
"""
import os

import pytest

from natlean import (Argument, Attack, ClaudeBackend, EvidenceIndex, Inference, JevBackend, NatLean, Prop,
                     weakest_links)
from natlean.estimate import estimate_prop

SOCRATES = "人はみな死ぬ。ソクラテスは人である。ゆえに、ソクラテスは死ぬ。"
FALLACY = "人はみな死ぬ。ソクラテスは死ぬ。ゆえに、ソクラテスは人である。"
HASTY = "昨日見たカラスは黒かった。今日見たカラスも黒かった。ゆえに、世界中のカラスはすべて黒い。"
GENERIC = "鳥は飛ぶ。ペンギンは鳥である。ゆえに、ペンギンは飛ぶ。"
HAM = "永遠の幸福にまさるものは何もない。ハムサンドは何もないよりはましである。ゆえに、ハムサンドは永遠の幸福にまさる。"
PENGUIN = "鳥は飛ぶ。ピーちゃんは鳥である。ゆえに、ピーちゃんは飛ぶ。ただし、ピーちゃんはペンギンである。"


def needs(*envs):
    missing = [e for e in envs if not os.environ.get(e)]
    return pytest.mark.skipif(bool(missing), reason=f"{', '.join(missing)} 未設定")


claude_api = lambda fn: pytest.mark.api(needs("ANTHROPIC_API_KEY")(fn))
jev_api = lambda fn: pytest.mark.api(pytest.mark.jev(needs("ANTHROPIC_API_KEY", "TYPESAFE_API_KEY")(fn)))


@pytest.fixture(scope="module")
def jev():
    return NatLean(JevBackend(), lang="en")


def top(res):
    return res.propagation.props[res.goals[-1]]


@jev_api
def test_jev_socrates_valid(jev):
    res = jev.check(SOCRATES)
    assert len(res.argument.props) == 3
    assert top(res).lo >= 0.8 and res.ok


@jev_api
def test_jev_affirming_the_consequent(jev):
    assert top(jev.check(FALLACY)).hi < 0.5


@jev_api
def test_jev_hasty_induction(jev):
    assert top(jev.check(HASTY)).lo < 0.5


@jev_api
def test_jev_penguin_undercut_is_the_weakest_link(jev):
    # 抽出は確率的なので、判定部分は手で作ったグラフで確かめる
    arg = Argument(
        language="ja",
        props=[Prop("p1", "鳥は飛ぶ"), Prop("p2", "ピーちゃんは鳥である"), Prop("p3", "ピーちゃんは飛ぶ", "conclusion"),
               Prop("p4", "ピーちゃんはペンギンである")],
        inferences=[Inference("s1", ["p1", "p2"], "p3", "generic_application")],
        attacks=[Attack("undercut", "p4", "s1")])
    res = jev.check_argument(arg)
    assert not res.ok
    assert res.propagation.edges["s1"].r_eff_lo < 0.5  # 掘り崩しで推論の r が下がる
    assert weakest_links(arg, "p3")[0][:2] == ("attack", "a1")


@jev_api
def test_jev_extracts_penguin_attack_most_of_the_time(jev):
    res = jev.check(PENGUIN)
    assert not res.ok
    if not res.argument.attacks:
        pytest.skip("今回の抽出では掘り崩しが見つからなかった（抽出は確率的）")


@jev_api
def test_jev_generic_sentence_is_read_in_two_ways(jev):
    res = jev.check(GENERIC)
    assert not res.ok
    # 抽出が曖昧さを見つけたときは、全称と総称の両方の意味に確率が付き、合計 1 になる
    for a in res.argument.ambiguities:
        assert sum(s.w for s in a.senses) == pytest.approx(1.0)
    if res.argument.ambiguities:
        assert res.mixture and res.mixture.evaluated >= 2


@jev_api
def test_jev_ham_sandwich_is_not_proved(jev):
    assert not jev.check(HAM).ok


@claude_api
def test_claude_backend_socrates():
    res = NatLean(ClaudeBackend(samples=3), lang="en").check(SOCRATES)
    assert top(res).lo >= 0.8


@claude_api
def test_claude_backend_fallacy():
    res = NatLean(ClaudeBackend(samples=3), lang="en").check(FALLACY)
    assert top(res).hi < 0.5


# ---------- 根拠文書 ----------

DOC = ("ソクラテスは古代ギリシャの哲学者である。紀元前399年に裁判で死刑の判決を受け、毒杯をあおいで死んだ。\n\n"
       "プラトンはソクラテスの弟子であり、アカデメイアを創設した。")


@jev_api
def test_jev_evidence_supports_and_contradicts():
    ix = EvidenceIndex({"socrates.txt": DOC})
    model = JevBackend()
    iv, cites, _ = estimate_prop(model, Prop("p1", "ソクラテスは毒杯をあおいで死んだ"), "ja", ix)
    assert iv.est > 0.8 and cites and cites[0].relation == "supports"
    iv, cites, _ = estimate_prop(model, Prop("p2", "ソクラテスは裁判で無罪になった"), "ja", ix)
    assert iv.est < 0.3 and cites and cites[0].relation == "contradicts"


@jev_api
def test_jev_no_relevant_evidence_falls_back_with_warning():
    ix = EvidenceIndex({"socrates.txt": DOC})
    _, cites, warns = estimate_prop(JevBackend(), Prop("p1", "東京は日本の首都である"), "ja", ix)
    assert not cites and [w.code for w in warns] == ["no_evidence"]
