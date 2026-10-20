"""NatLean: 自然言語版 Lean — 自然言語の論証を確率の区間としてステップごとにチェックする"""

__version__ = "0.2.0"

from .checker import NatLean, Result  # noqa: E402
from .decision import CachedModel, ClaudeBackend, FakeBackend, JevBackend, make_backend  # noqa: E402
from .evidence import EvidenceIndex  # noqa: E402
from .graph import Argument, Attack, Cite, Inference, Interval, Prop  # noqa: E402
from .propagate import Propagation, goals, propagate, status, weakest_links  # noqa: E402
from .report import report, to_json  # noqa: E402

__all__ = [
    "__version__", "NatLean", "Result", "report", "to_json",
    "Argument", "Prop", "Inference", "Attack", "Interval", "Cite", "EvidenceIndex",
    "propagate", "goals", "status", "weakest_links", "Propagation",
    "make_backend", "JevBackend", "ClaudeBackend", "FakeBackend", "CachedModel",
]
