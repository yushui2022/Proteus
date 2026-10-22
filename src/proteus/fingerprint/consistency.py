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


#: Display-scaling steps each OS actually offers. Windows exposes the
#: 100/125/150/175/200/250/300% menu; macOS reports 1 or 2 and nothing in
#: between (a Mac driving a non-Retina external display really does report 1);
#: Linux gives 1, the GNOME fractional 1.25/1.5/1.75 steps, and 2 under HiDPI.
#: Mid-step values such as 1.818 or 1.09 are a browser zoom level leaking into
#: the ratio, not a display mode.
PLAUSIBLE_DPR = {
    "windows": (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0),
    "macos": (1.0, 2.0),
    "linux": (1.0, 1.25, 1.5, 1.75, 2.0),
}


def _dpr_implausible(fp: Fingerprint) -> Optional[str]:
    dpr = float(fp.device_pixel_ratio)
    if dpr <= 0:
        return f"device_pixel_ratio must be positive, got {dpr!r}"
    allowed = PLAUSIBLE_DPR.get(fp.os_family)
    if allowed and dpr not in allowed:
        return (
            f"devicePixelRatio={dpr!r} is not a display mode {fp.os_family} "
            f"offers (allowed: {allowed})"
        )
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


#: Apple Silicon core counts. Physical == logical there is no SMT, and 11 is
#: real: an M3 Pro is 6 performance + 5 efficiency cores. An explicit set rather
#: than a range, because 9, 13 and 15 are not Apple parts.
APPLE_SILICON_CORES = frozenset({8, 10, 11, 12, 14, 16})


def _concurrency_range(fp: Fingerprint) -> Optional[str]:
    n = fp.hardware_concurrency
    if not isinstance(n, int) or n < 2 or n > 64:
        return f"hardwareConcurrency={n!r} outside the plausible range 2..64"
    # Apple Silicon reports physical == logical and ships odd counts (an M3 Pro
    # is 6P+5E = 11), so the even-count expectation only holds on x86.
    if fp.os_family != "macos" and n % 2 != 0:
        return (
            f"hardwareConcurrency={n} is odd; x86 parts expose SMT and report "
            f"even counts"
        )
    return None


def _apple_silicon_cores(fp: Fingerprint) -> Optional[str]:
    """Cross-pool rule: an Apple M-series GPU implies an Apple Silicon core count."""
    if fp.os_family != "macos" or "Apple M" not in fp.webgl_renderer:
        return None
    n = fp.hardware_concurrency
    if n not in APPLE_SILICON_CORES:
        return (
            f"renderer {fp.webgl_renderer!r} implies Apple Silicon, whose core "
            f"counts are {sorted(APPLE_SILICON_CORES)}; got {n}"
        )
    return None


def _device_memory_range(fp: Fingerprint) -> Optional[str]:
    # navigator.deviceMemory is the approximate device RAM rounded up to a power
    # of two. Measured: a 32 GB Windows machine reports 32 under Chromium 155,
    # so 16 and 32 are legitimate values. An earlier version of this rule
    # claimed Chromium caps at 8 and would have rejected real machines.
    allowed = (1, 2, 4, 8, 16, 32)
    if fp.device_memory not in allowed:
        return f"deviceMemory={fp.device_memory!r} not in {allowed}"
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
    Rule("hardware.apple_silicon_cores", FATAL, _apple_silicon_cores),
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
