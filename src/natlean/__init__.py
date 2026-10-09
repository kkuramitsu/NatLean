"""NatLean: 自然言語版 Lean — 自然言語の論証をステップごとに確率的にチェックする"""

__version__ = "0.0.1"

from .core import (  # noqa: E402
    DEFAULT_MODEL,
    LABEL_SCORE,
    PATTERN_CAP,
    Claim,
    NatLean,
    Verdict,
    propagate,
    report,
)

__all__ = [
    "__version__",
    "DEFAULT_MODEL",
    "LABEL_SCORE",
    "PATTERN_CAP",
    "Claim",
    "NatLean",
    "Verdict",
    "propagate",
    "report",
]
