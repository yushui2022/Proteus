"""Data models for the Proteus fingerprint engine.

Everything here is immutable. A :class:`Fingerprint` is the single source of
truth for "what this profile claims to be"; a :class:`Violation` is a
machine-readable statement that the claim contradicts itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

#: Countries with a built-in geo sample. Deliberately small for M0 —
#: the real geoIP lookup lands in M2 (see docs/ROADMAP.md).
_COUNTRY_GEO = {
    "US": ("America/New_York", "en-US", ("en-US", "en"), 40.7128, -74.0060),
    "GB": ("Europe/London", "en-GB", ("en-GB", "en"), 51.5074, -0.1278),
    "DE": ("Europe/Berlin", "de-DE", ("de-DE", "de", "en"), 52.5200, 13.4050),
    "FR": ("Europe/Paris", "fr-FR", ("fr-FR", "fr", "en"), 48.8566, 2.3522),
    "NL": ("Europe/Amsterdam", "nl-NL", ("nl-NL", "nl", "en"), 52.3676, 4.9041),
    "JP": ("Asia/Tokyo", "ja-JP", ("ja-JP", "ja"), 35.6762, 139.6503),
    "SG": ("Asia/Singapore", "en-SG", ("en-SG", "en", "zh-CN"), 1.3521, 103.8198),
    "CN": ("Asia/Shanghai", "zh-CN", ("zh-CN", "zh"), 31.2304, 121.4737),
    "BR": ("America/Sao_Paulo", "pt-BR", ("pt-BR", "pt"), -23.5505, -46.6333),
}

SUPPORTED_COUNTRIES: Tuple[str, ...] = tuple(sorted(_COUNTRY_GEO))


@dataclass(frozen=True)
class GeoProfile:
    """Where the profile's traffic appears to come from.

    This is *derived from the proxy's exit IP*, never from the seed. Timezone
    and locale are hard constraints: a profile behind a German exit that reports
    ``Asia/Shanghai`` is trivially detectable, no matter how good the rest of
    the fingerprint is. See docs/adr/0002-fingerprint-consistency.md.
    """

    country: str
    timezone: str
    locale: str
    languages: Tuple[str, ...]
    latitude: float = 0.0
    longitude: float = 0.0

    def __post_init__(self) -> None:
        if not self.country:
            raise ValueError("country is required")
        if not self.languages:
            raise ValueError("languages must not be empty")

    @property
    def language(self) -> str:
        """Primary language subtag, e.g. ``de`` for ``de-DE``."""
        return self.locale.split("-")[0].lower()

    @classmethod
    def for_country(cls, country: str) -> "GeoProfile":
        """Build a sample geo profile for *country* (ISO 3166-1 alpha-2)."""
        code = (country or "").upper()
        if code not in _COUNTRY_GEO:
            raise ValueError(
                f"no built-in geo sample for {country!r}; "
                f"known: {', '.join(SUPPORTED_COUNTRIES)}"
            )
        tz, locale, languages, lat, lon = _COUNTRY_GEO[code]
        return cls(
            country=code,
            timezone=tz,
            locale=locale,
            languages=languages,
            latitude=lat,
            longitude=lon,
        )


@dataclass(frozen=True)
class Violation:
    """A self-contradiction inside a fingerprint.

    ``code`` is a stable public identifier (``<domain>.<problem>``). Users quote
    these in bug reports, so they must never be renamed once released.
    """

    code: str
    severity: str  # "fatal" | "warn"
    message: str

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return f"[{self.severity}] {self.code}: {self.message}"


@dataclass(frozen=True)
class Fingerprint:
    """The complete set of claims one profile makes about its device."""

    seed: int
    geo: GeoProfile

    os_family: str  # "windows" | "macos" | "linux"
    platform: str  # navigator.platform
    ua: str
    ua_major: int

    screen_width: int
    screen_height: int
    device_pixel_ratio: float

    hardware_concurrency: int
    device_memory: int

    webgl_vendor: str
    webgl_renderer: str
    font_profile: str

    canvas_noise: int
    audio_noise: float

    @property
    def timezone(self) -> str:
        return self.geo.timezone

    @property
    def locale(self) -> str:
        return self.geo.locale

    @property
    def languages(self) -> Tuple[str, ...]:
        return self.geo.languages

    @property
    def country(self) -> str:
        return self.geo.country
