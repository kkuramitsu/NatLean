"""NatLean のテスト

    pytest -v                 # 全部（API を呼ぶテストを含む）
    pytest -v -m "not api"    # オフラインのみ
"""
import os

import pytest

from natlean import Claim, NatLean, Verdict, propagate

SOCRATES = "人はみな死ぬ。ソクラテスとは人である。ゆえに、ソクラテスは死ぬ。"
# 後件肯定の誤謬
SOCRATES_FALLACY = "人はみな死ぬ。ソクラテスは死ぬ。ゆえに、ソクラテスは人である。"
# 過度な一般化（帰納）
HASTY_INDUCTION = "昨日見たカラスは黒かった。今日見たカラスも黒かった。ゆえに、世界中のカラスはすべて黒い。"


# ---------- オフライン: 伝播ロジック ----------

def test_propagate_deduction_valid():
    claims = [
        Claim("c1", "人はみな死ぬ", "premise"),
        Claim("c2", "ソクラテスは人である", "premise"),
        Claim("c3", "ソクラテスは死ぬ", "conclusion", ["c1", "c2"], "deduction",
              Verdict(1.0, 0.0, ["valid"] * 3, "")),
    ]
    propagate(claims)
    assert claims[2].conf == pytest.approx(1.0)


def test_propagate_chain_multiplies():
    claims = [
        Claim("c1", "A", "premise"),
        Claim("c2", "B", "inference", ["c1"], "induction", Verdict(0.75, 0.0, [], "")),
        Claim("c3", "C", "conclusion", ["c2"], "deduction", Verdict(1.0, 0.0, [], "")),
    ]
    propagate(claims)
    assert claims[1].conf == pytest.approx(0.75 * 0.8)  # 帰納は上限 0.8
    assert claims[2].conf == pytest.approx(0.75 * 0.8)  # 弱い前提が結論に伝播


# ---------- API: Haiku で実際に判定 ----------

def api(fn):
    """API を呼ぶテスト: -m "not api" で除外でき、キーが無ければスキップ"""
    skip = pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY 未設定")
    return pytest.mark.api(skip(fn))


@pytest.fixture(scope="module")
def checker():
    return NatLean(samples=3)


def goal(claims):
    return [c for c in claims if c.role == "conclusion"][-1]


@api
def test_socrates_valid(checker):
    claims = checker.check(SOCRATES)
    g = goal(claims)
    assert len(claims) == 3
    assert g.pattern == "deduction"
    assert set(g.depends_on) == {"c1", "c2"}
    assert g.conf >= 0.8


@api
def test_socrates_fallacy(checker):
    g = goal(checker.check(SOCRATES_FALLACY))
    assert g.conf < 0.5


@api
def test_hasty_induction(checker):
    g = goal(checker.check(HASTY_INDUCTION))
    assert g.pattern == "induction"
    assert g.conf < 0.8
