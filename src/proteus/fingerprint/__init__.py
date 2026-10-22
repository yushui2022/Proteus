"""Fingerprint engine: derive a self-consistent fingerprint, then verify it.

Typical use::

    from proteus.fingerprint import GeoProfile, derive, check

    fp = derive(seed=42, geo=GeoProfile.for_country("DE"))
    if check(fp):
        raise SystemExit("refusing to launch an inconsistent profile")
"""

from __future__ import annotations

from .consistency import FATAL, RULE_CODES, RULES, WARN, check, fatal_only, is_consistent
from .derive import (
    CHROME_MAJORS,
    OS_FAMILIES,
    OS_PROFILES,
    build_ua,
    derive,
    derive_for_country,
    index_of,
    pick,
)
from .model import SUPPORTED_COUNTRIES, Fingerprint, GeoProfile, Violation

__all__ = [
    "CHROME_MAJORS",
    "FATAL",
    "Fingerprint",
    "GeoProfile",
    "OS_FAMILIES",
    "OS_PROFILES",
    "RULES",
    "RULE_CODES",
    "SUPPORTED_COUNTRIES",
    "Violation",
    "WARN",
    "build_ua",
    "check",
    "derive",
    "derive_for_country",
    "fatal_only",
    "index_of",
    "is_consistent",
    "pick",
]
