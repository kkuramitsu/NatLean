# CLAUDE.md

NatLean は「自然言語版 Lean」。自然言語の論証を主張に分割し、推論ステップごとに軽量 LLM（Claude Haiku）で妥当性を判定して、確率（信頼度）として伝播させる。

## 構成

- `src/natlean/core.py` — 本体。スキーマ（Pydantic）、プロンプト、`NatLean` クラス、`propagate`、`report`
- `src/natlean/cli.py` — `natlean` コマンド（argparse）
- `src/natlean/__init__.py` — 公開 API と `__version__`（バージョンの唯一の定義元）
- `tests/test_natlean.py` — オフラインテスト（伝播ロジック）と `@api` テスト（実 API）
- `examples/` — サンプル入力（正しい演繹・誤謬・過度な一般化）

## パイプライン

1. `NatLean.segment` — 1回の LLM 呼び出しで、主張・役割・`depends_on`・推論パターンを抽出
2. `NatLean.check_step` — ステップごとに `samples` 回並列で判定し、ラベルを `LABEL_SCORE` で数値化して平均
3. `propagate` — `score × PATTERN_CAP[pattern] × Π conf(依存先)`。claims が出現順であることを前提にしている
4. `report` — Lean 風テキスト出力

## コマンド

```bash
pip install -e ".[dev]"
pytest -m "not api"          # オフライン（速い・無料）
pytest                       # 実 API を呼ぶ（ANTHROPIC_API_KEY 必須、数十秒、課金あり）
natlean examples/fallacy.txt
python -m build && twine check dist/*
```

## 規約

- コメント・docstring・プロンプト・CLI のメッセージは日本語。
- LLM 呼び出しは Anthropic 公式 SDK の `client.messages.parse(output_format=PydanticModel)` で構造化出力を受け取る。文字列を自前でパースしない。
- 既定モデルは `claude-haiku-5-5`（`DEFAULT_MODEL`）。Haiku 5.5 は `temperature` などのサンプリング引数を既定値以外にすると 400 になるので渡さない。
- 推論パターンを追加するときは `Pattern`、`PATTERN_CAP`、`PATTERN_CRITERIA`、`SEGMENT_SYSTEM` の4か所をそろえて更新する。
- 判定ロジックやプロンプトを変えたら、オフラインテストに加えて `pytest -m api` で実 API の挙動も確認する。
- バージョンを上げるときは `src/natlean/__init__.py` の `__version__` だけを変える。

## 今後の課題

- 前提の事実確認モード
- 正解ラベル付きデータ（FOLIO、EntailmentBank など）によるスコアの校正
- 「?」になったステップだけ上位モデルで再判定
- 判定結果のキャッシュによる増分チェック
