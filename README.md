# NatLean — 自然言語版 Lean

[![CI](https://github.com/kkuramitsu/NatLean/actions/workflows/ci.yml/badge.svg)](https://github.com/kkuramitsu/NatLean/actions/workflows/ci.yml)

NatLean は、自然言語で書かれた論証を **Lean のように1ステップずつ検証する** ツールです。

論証を命題と推論のグラフに分け、各推論について「前提がすべて真なら結論が真である確率」を
決定モデル（[Jev](https://typesafe.ai) または Claude Haiku）で推定し、結論がどれだけ支えられているかを
**確率の区間**（依存を仮定しない下限、独立を仮定した推定、上限）として示します。弱いステップは `sorry` として、
結論の下限を最も押し下げている要素（最も弱い環）とともに指摘します。

```
$ natlean examples/fallacy.txt --lang en
p1  [premise] すべての人は死ぬ    assumed
p2  [premise] ソクラテスは死ぬ    assumed
p3  [conclusion] ソクラテスは人である    ✗ L=0.06 P̂=0.07 U=0.09  sorry
      s1: p1, p2 ⊢ p3  [deduction]  r=[0.06, 0.09]

Goal p3: NOT PROVED (lower bound 0.06)
  weakest links:
    inference s1 (+0.94)
```

表示は日本語と英語に対応しています（`--lang ja|en`）。

## インストール

```bash
pip install natlean          # Python 3.10 以上
export ANTHROPIC_API_KEY=sk-ant-...     # 論証の抽出に使う
export TYPESAFE_API_KEY=...             # Jev を使う場合（無ければ Claude で判定）
```

## 使い方

```bash
natlean examples/deduction.txt          # ファイルを検証
echo "…" | natlean -                    # 標準入力から
natlean essay.txt --lang en             # 英語で表示（既定は NATLEAN_LANG、LANG の順に判定）
natlean essay.txt --mode estimate       # 前提の確かさも推定する（既定の assume は前提を真と置く）
natlean essay.txt --evidence docs/        # 根拠文書（ファイルまたはディレクトリ、複数可）で前提の確かさを推定
natlean essay.txt --backend claude      # 判定を Claude で行う
natlean essay.txt --no-interpret       # 曖昧さの解釈の混合をしない
natlean essay.txt --threshold 0.7       # 「証明済み」とみなす下限のしきい値
natlean essay.txt --log decisions.jsonl # 判断ログ兼キャッシュ
natlean essay.txt --json                # JSON で出力
```

終了コードは、すべての結論の下限がしきい値以上なら `0`、そうでなければ `1`、エラーは `2` です。

```python
from natlean import NatLean, report

res = NatLean(lang="ja").check("人はみな死ぬ。ソクラテスは人である。ゆえに、ソクラテスは死ぬ。")
print(report(res))
print(res.ok, res.propagation.props[res.goals[0]])
```

## 仕組み

| Lean | NatLean |
|---|---|
| 仮定 `h : P` | 前提（確かさ p） |
| ゴール `⊢ Q` | 結論 |
| タクティク1ステップ | 推論1ステップ（確かさ r） |
| 型検査 OK / エラー | 下限 L による ✓ / ? / ✗ |
| `sorry` | 根拠不足のステップ |

1. **抽出**: Claude が命題・推論（演繹、総称の適用、部分クラス、帰納など）・攻撃（反駁と掘り崩し）を抽出する。
2. **推定**: 決定モデルが r（と必要なら p）を、言い換え・否定・2系統の問いで複数回問い、最小〜最大の区間にする。
   決定モデルには論証の全文を見せず、前提と結論だけを渡す（説得力ではなく論理的な支持を測るため）。
3. **伝播**（コードのみ）: 下限は `r.lo × max(0, 1 − Σ(1 − 前提の下限))`、上限は `1 − q.lo × (1 − r.hi)`。
   掘り崩しは r を下げ、反駁は上限を下げる。閉路上の推論は使わない。
4. **解釈の混合**: 「鳥は飛ぶ」（全称か総称か）や、途中で意味が変わる語のような曖昧さは、意味ごとに命題を書き換えて
   グラフ全体を評価し、意味の確からしさで混合する。読み方で結論の下限が変わるときと、
   「全称と読めば推論は妥当だが前提が偽、総称と読めば前提は真だが推論が弱い」のように
   読み替えで成り立って見えるとき（多義の誤謬。`--mode estimate` のみ）は警告する。
5. **根拠文書**（`--evidence`）: 前提を根拠文書の該当箇所（passage）に照らして `P(前提 | 根拠)` として推定し、
   どの出どころ（ファイル）の何番目の passage に基づくかをレポートに示す。同じ出どころに基づく複数の根拠は独立とみなさず、
   二重計上を警告する。
6. **判定**: `L ≥ threshold` で ✓、独立なら成立（`P̂ ≥ threshold`）で ?、それ未満は ✗（sorry）。

設計の詳細は [`tex/design.tex`](tex/design.tex) にあります。

## 制限事項

- `assume` モードでは前提の真偽は検証しません（すべて仮定として受け入れます）。
- 確率は決定モデルの出力で、まだ校正（calibration）していません。
- 根拠文書の検索は文字 2-gram の重なりだけで、意味的な検索ではありません。常識的な前提は、関連の薄い passage に
  引きずられて根拠なしの推定より低くなることがあります。
- 曖昧さの抽出は LLM によるため、実行ごとに見つかったり見つからなかったりします（多義の誤謬は特に揺れます）。
- Jev は早期アクセスで、`jev-latest` の中身が変わりえます。応答のバージョンを判断ログ（`--log`）に残します。

## 開発

```bash
pip install -e ".[dev]"
pytest -m "not api"     # オフラインのテストのみ
pytest -m api           # 実 API を呼ぶテスト（ANTHROPIC_API_KEY、Jev は TYPESAFE_API_KEY も必要）
```

## ライセンス

MIT
