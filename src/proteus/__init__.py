"""Proteus — self-hostable anti-detect browser core and orchestration framework.

M0 implements the fingerprint engine only: deterministic, reproducible
derivation plus a consistency rule set. Kernel adapters, profile isolation, the
proxy orchestrator and the HTTP API are tracked in ``docs/ROADMAP.md``.

Licensed AGPL-3.0. See ``docs/ACCEPTABLE-USE-POLICY.md`` before using this.
"""

from __future__ import annotations

__version__ = "0.1.0"
__status__ = "M0"

__all__ = ["__status__", "__version__"]
