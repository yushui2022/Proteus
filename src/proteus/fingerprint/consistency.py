"""Fingerprint consistency rules.

A fingerprint is not "good" because it is unusual — it is good because it does
not contradict itself. These rules encode that judgement, and every one of them
has a stable public code, because bug reports quote codes, not prose.

Any ``fatal`` violation must prevent a profile from launching. Starting a
browser that is trivially identifiable is worse than failing loudly: it burns
the device trust a user has been accumulating.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple

from .derive import OS_PROFILES
from .model import Fingerprint, Violation

FATAL = "fatal"
WARN = "warn"

#: Message factory: returns ``None`` when the fingerprint satisfies the rule.
RuleFn = Callable[[Fingerprint], Optional[str]]


@dataclass(frozen=True)
class Rule:
    code: str
    severity: str
    fn: RuleFn

    def evaluate(self, fp: Fingerprint) -> Optional[Violation]:
        message = self.fn(fp)
        if message is None:
            return None
        return Violation(code=self.code, severity=self.severity, message=message)


def _table(fp: Fingerprint) -> Optional[dict]:
    return OS_PROFILES.get(fp.os_family)


# --------------------------------------------------------------------------
# OS vs everything else
# --------------------------------------------------------------------------


def _platform_mismatch(fp: Fingerprint) -> Optional[str]:
    table = _table(fp)
    if table is None:
        return f"unknown os_family {fp.os_family!r}"
    expected = table["platform"]
    if fp.platform != expected:
        return f"os_family={fp.os_family!r} implies navigator.platform={expected!r}, got {fp.platform!r}"
    return None


def _ua_mismatch(fp: Fingerprint) -> Optional[str]:
    table = _table(fp)
    if table is None:
        return f"unknown os_family {fp.os_family!r}"
    expected = table["ua_os"]
    if expected not in fp.ua:
        return f"os_family={fp.os_family!r} implies user-agent OS token {expected!r}, not found in {fp.ua!r}"
    return None


def _font_profile_mismatch(fp: Fingerprint) -> Optional[str]:
    if not fp.font_profile.startswith(fp.os_family):
        return (
            f"font_profile {fp.font_profile!r} does not belong to os_family "
            f"{fp.os_family!r} — a windowed font set on a non-matching platform "
            f"is a classic giveaway"
        )
    return None


def _webgl_vendor_mismatch(fp: Fingerprint) -> Optional[str]:
    table = _table(fp)
    if table is None:
        return f"unknown os_family {fp.os_family!r}"
    expected = table["webgl_vendor"]
    if fp.webgl_vendor != expected:
        return f"os_family={fp.os_family!r} implies WebGL vendor {expected!r}, got {fp.webgl_vendor!r}"
    return None


def _dpr_implausible(fp: Fingerprint) -> Optional[str]:
    dpr = fp.device_pixel_ratio
    if dpr <= 0:
        return f"device_pixel_ratio must be positive, got {dpr!r}"
    if fp.os_family == "macos" and dpr < 2.0:
        return f"macOS profiles report DPR >= 2.0 on Retina hardware, got {dpr!r}"
    if fp.os_family in ("windows", "linux") and dpr > 2.0:
        return f"{fp.os_family} profiles do not plausibly report DPR > 2.0, got {dpr!r}"
    return None


# --------------------------------------------------------------------------
# User agent vs client hints
# --------------------------------------------------------------------------


def _ua_major_mismatch(fp: Fingerprint) -> Optional[str]:
    token = f"Chrome/{fp.ua_major}."
    if token not in fp.ua:
        return (
            f"ua_major={fp.ua_major} disagrees with the user-agent string {fp.ua!r}; "
            f"sec-ch-ua would expose the same disagreement"
        )
    return None


# --------------------------------------------------------------------------
# Hardware
# --------------------------------------------------------------------------


def _concurrency_range(fp: Fingerprint) -> Optional[str]:
    n = fp.hardware_concurrency
    if not isinstance(n, int) or n < 2 or n > 64:
        return f"hardwareConcurrency={n!r} outside the plausible range 2..64"
    if n % 2 != 0:
        return f"hardwareConcurrency={n} is odd; real consumer CPUs report even core counts"
    return None


def _device_memory_range(fp: Fingerprint) -> Optional[str]:
    # Chromium clamps navigator.deviceMemory to 8, so 16/32 is an immediate tell.
    allowed = (1, 2, 4, 8)
    if fp.device_memory not in allowed:
        return f"deviceMemory={fp.device_memory!r} not in {allowed} (Chromium caps at 8)"
    return None


# --------------------------------------------------------------------------
# Screen
# --------------------------------------------------------------------------


def _screen_geometry(fp: Fingerprint) -> Optional[str]:
    w, h = fp.screen_width, fp.screen_height
    if w <= 0 or h <= 0:
        return f"screen {w}x{h} must be positive"
    if w < h:
        return f"screen {w}x{h} is portrait; desktop profiles should report landscape"
    if w > 15360 or h > 8640:
        return f"screen {w}x{h} exceeds any plausible desktop resolution"
    return None


# --------------------------------------------------------------------------
# Locale / geo
# --------------------------------------------------------------------------


def _language_mismatch(fp: Fingerprint) -> Optional[str]:
    if not fp.languages:
        return "navigator.languages must not be empty"
    primary = fp.languages[0].split("-")[0].lower()
    expected = fp.locale.split("-")[0].lower()
    if primary != expected:
        return (
            f"navigator.languages[0]={fp.languages[0]!r} contradicts locale {fp.locale!r}"
        )
    return None


def _timezone_format(fp: Fingerprint) -> Optional[str]:
    tz = fp.timezone
    if not tz:
        return "timezone must not be empty"
    if tz != "UTC" and "/" not in tz:
        return f"timezone {tz!r} is not an IANA zone name"
    return None


# --------------------------------------------------------------------------
# Deterministic noise
# --------------------------------------------------------------------------


def _canvas_noise_range(fp: Fingerprint) -> Optional[str]:
    if not -128 <= fp.canvas_noise <= 127:
        return f"canvas_noise={fp.canvas_noise!r} outside the intended -128..127 band"
    return None


def _audio_noise_range(fp: Fingerprint) -> Optional[str]:
    if abs(fp.audio_noise) > 1e-4:
        return f"audio_noise={fp.audio_noise!r} would alter AudioContext output audibly"
    return None


RULES: Tuple[Rule, ...] = (
    Rule("os.platform_mismatch", FATAL, _platform_mismatch),
    Rule("os.ua_mismatch", FATAL, _ua_mismatch),
    Rule("os.font_profile_mismatch", FATAL, _font_profile_mismatch),
    Rule("os.webgl_vendor_mismatch", FATAL, _webgl_vendor_mismatch),
    Rule("os.dpr_implausible", FATAL, _dpr_implausible),
    Rule("ua.major_mismatch", FATAL, _ua_major_mismatch),
    Rule("hardware.concurrency_range", FATAL, _concurrency_range),
    Rule("hardware.device_memory_range", FATAL, _device_memory_range),
    Rule("screen.geometry", FATAL, _screen_geometry),
    Rule("locale.language_mismatch", FATAL, _language_mismatch),
    Rule("geo.timezone_format", WARN, _timezone_format),
    Rule("noise.canvas_range", WARN, _canvas_noise_range),
    Rule("noise.audio_range", WARN, _audio_noise_range),
)

RULE_CODES: Tuple[str, ...] = tuple(rule.code for rule in RULES)


def check(fp: Fingerprint) -> List[Violation]:
    """Return every rule violation for *fp*, in rule order."""
    found: List[Violation] = []
    for rule in RULES:
        violation = rule.evaluate(fp)
        if violation is not None:
            found.append(violation)
    return found


def fatal_only(violations: Iterable[Violation]) -> List[Violation]:
    return [v for v in violations if v.severity == FATAL]


def is_consistent(fp: Fingerprint) -> bool:
    """True when *fp* has no violation at all (fatal or otherwise)."""
    return not check(fp)
