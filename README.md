# NatLean — 自然言語版 Lean

[![CI](https://github.com/kkuramitsu/NatLean/actions/workflows/ci.yml/badge.svg)](https://github.com/kkuramitsu/NatLean/actions/workflows/ci.yml)

NatLean は、自然言語で書かれた論証を **Lean のように1ステップずつ検証する** ツールです。

自然言語では厳密な証明検査ができないため、各推論ステップの妥当性を軽量 LLM（Claude Haiku）で判定し、
**確率（信頼度）** として扱います。文章を主張に分割し、文と文のあいだの推論パターン
（演繹・帰納・アブダクションなど）を調べ、弱いステップを `sorry` として指摘します。

```
$ echo "人はみな死ぬ。ソクラテスは死ぬ。ゆえに、ソクラテスは人である。" | natlean -
c1  [premise] 人はみな死ぬ    assumed
c2  [premise] ソクラテスは死ぬ    assumed
c3  [deduction] c1,c2 ⊢ ソクラテスは人である    ✗ 0.10  sorry
      └ invalid/invalid/invalid: 後件肯定の形式的誤謬であり、死ぬ別の存在(例:猫)を想定すれば反例が構成できる。

Goal c3: NOT PROVED (conf=0.10)
  weakest link: c3
```

## インストール

```bash
pip install natlean          # Python 3.10 以上
export ANTHROPIC_API_KEY=sk-ant-...
```

## 使い方

### コマンドライン

```bash
natlean examples/deduction.txt          # ファイルを検証
echo "…" | natlean -                    # 標準入力から
natlean essay.txt --samples 5           # 1ステップあたりの判定回数を増やす
natlean essay.txt --threshold 0.7       # 「証明済み」とみなす信頼度のしきい値
natlean essay.txt --json                # JSON で出力
natlean essay.txt --model claude-sonnet-5-5   # 判定モデルを変更
```

終了コードは、すべての結論がしきい値以上なら `0`、そうでなければ `1` です（CI に組み込めます）。

### Python から

```python
from natlean import NatLean, report

claims = NatLean(samples=3).check("人はみな死ぬ。ソクラテスは人である。ゆえに、ソクラテスは死ぬ。")
print(report(claims))
for c in claims:
    print(c.id, c.pattern, c.conf)
```

## 仕組み

| Lean | NatLean |
|---|---|
| 仮定 `h : P` | 前提（premise） |
| ゴール `⊢ Q` | 結論（conclusion） |
| タクティク1ステップ | 主張間の推論1ステップ |
| 型検査 OK / エラー | 確率スコア付き判定 ✓ / ? / ✗ |
| `sorry` | 根拠不足のステップ |

1. **分割・構造解析**: 文章を原子的な主張（claim）に分け、役割（premise / definition / inference / conclusion）、依存関係（`depends_on`）、推論パターンを付与する。
2. **ステップ検証**: 各推論ステップについて、パターン別の観点（演繹なら反例・形式的誤謬、帰納なら事例の代表性など）で Haiku に `valid / plausible / weak / invalid / contradicts` を判定させる。これを `--samples` 回繰り返して平均する。
3. **信頼度の伝播**:
   `conf(主張) = 平均スコア × パターン上限 × Π conf(前提)`
   パターン上限は演繹 1.0、帰納 0.8、アブダクション・因果 0.7、類推 0.6 など。
4. **判定**: `conf ≥ threshold` で ✓、`≥ 0.5` で ?、それ未満は ✗（sorry）。

## 制限事項

- 前提の真偽は検証しません（すべて仮定として受け入れます）。
- スコアは LLM の判定にもとづく推定値で、まだ校正（calibration）していません。
- 現在は主に日本語の文章を想定してプロンプトを書いています。

## 開発

```bash
pip install -e ".[dev]"
pytest -m "not api"     # オフラインのテストのみ
pytest                  # API を呼ぶテストを含む（ANTHROPIC_API_KEY が必要）
```

## ライセンス

MIT
