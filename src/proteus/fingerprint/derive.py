"""Deterministic fingerprint derivation.

Every field is computed as::

    idx = int.from_bytes(sha256(f"{seed}:{field_name}")[:8], "big") % len(choices)

Why not :mod:`random`? Three reasons, all of them product requirements:

1. **Cross-version stability.** ``random.Random(seed)`` has no documented
   guarantee that the same seed yields the same stream across CPython
   versions. SHA-256 does.
2. **Field independence.** Drawing from one shared RNG stream means inserting
   a new field shifts every later field — i.e. one upgrade silently re-rolls
   the fingerprint of every existing profile. Hashing per field removes that
   whole class of bug.
3. **Auditability.** A user can hand-compute why a profile got 2560x1440
   without reproducing hidden state.

Timezone, locale and languages are deliberately *not* derived from the seed:
they come from the proxy's geolocation. See ``GeoProfile``.
"""

from __future__ import annotations

import hashlib
from typing import Optional, Sequence, TypeVar

from .model import Fingerprint, GeoProfile

T = TypeVar("T")

CHROME_MAJORS: Sequence[int] = tuple(range(126, 136))

OS_FAMILIES: Sequence[str] = ("windows", "macos", "linux")

#: Per-OS candidate tables. Keeping these realistic matters more than making
#: them large: the goal is to land inside the real-device distribution, not to
#: be unique. A fingerprint nobody else has is a fingerprint worth remembering.
OS_PROFILES = {
    "windows": {
        "platform": "Win32",
        "ua_os": "Windows NT 10.0; Win64; x64",
        "webgl_vendor": "Google Inc. (NVIDIA)",
        "webgl_renderers": (
            "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "ANGLE (AMD, AMD Radeon RX 6600 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        ),
        "font_profile": "windows-11",
        # Windows exposes the display-scaling steps 100/125/150/175/200/250/300%.
        "device_pixel_ratios": (1.0, 1.25, 1.5, 1.75, 2.0, 2.5),
        "screens": (
            (1920, 1080),
            (2560, 1440),
            (3840, 2160),
            (1366, 768),
            (1600, 900),
            (1536, 864),
        ),
        "hardware_concurrency": (4, 6, 8, 12, 16, 20, 24),
        # Measured on this project: a 32 GB Windows machine reports
        # navigator.deviceMemory == 32 under Chromium 155. The value is NOT
        # capped at 8, which is what an earlier version of this table assumed.
        "device_memory": (8, 16, 32),
    },
    "macos": {
        "platform": "MacIntel",
        "ua_os": "Macintosh; Intel Mac OS X 10_15_7",
        "webgl_vendor": "Google Inc. (Apple)",
        "webgl_renderers": (
            "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)",
            "ANGLE (Apple, ANGLE Metal Renderer: Apple M2 Pro, Unspecified Version)",
            "ANGLE (Apple, ANGLE Metal Renderer: Apple M3, Unspecified Version)",
        ),
        "font_profile": "macos-sonoma",
        # macOS reports 1 or 2 and nothing between: a Mac driving a non-Retina
        # external display genuinely reports 1.
        "device_pixel_ratios": (1.0, 2.0),
        "screens": (
            (1440, 900),
            (1512, 982),
            (1728, 1117),
            (1920, 1080),
            (2560, 1440),
            (3456, 2234),
        ),
        # 11 is real: an M3 Pro is 6 performance + 5 efficiency cores, and
        # Apple Silicon has no SMT, so the count stays odd.
        "hardware_concurrency": (8, 10, 11, 12),
        "device_memory": (8, 16, 32),
    },
    "linux": {
        "platform": "Linux x86_64",
        "ua_os": "X11; Linux x86_64",
        "webgl_vendor": "Google Inc. (Intel)",
        "webgl_renderers": (
            "ANGLE (Intel, Mesa Intel(R) UHD Graphics 630 (CFL GT2), OpenGL 4.6)",
            "ANGLE (Intel, Mesa Intel(R) Xe Graphics (TGL GT2), OpenGL 4.6)",
        ),
        "font_profile": "linux-ubuntu-24.04",
        "device_pixel_ratios": (1.0, 1.25, 2.0),
        "screens": ((1920, 1080), (2560, 1440), (1366, 768)),
        "hardware_concurrency": (4, 8, 16),
        "device_memory": (4, 8, 16),
    },
}


def index_of(seed: int, field: str, modulus: int) -> int:
    """Return a stable index in ``[0, modulus)`` for ``(seed, field)``."""
    if modulus <= 0:
        raise ValueError("modulus must be positive")
    digest = hashlib.sha256(f"{seed}:{field}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % modulus


def pick(seed: int, field: str, choices: Sequence[T]) -> T:
    """Deterministically choose one element of *choices* for ``(seed, field)``."""
    if not choices:
        raise ValueError("choices must not be empty")
    return choices[index_of(seed, field, len(choices))]


def build_ua(os_family: str, major: int) -> str:
    """Compose a Chrome user-agent string that matches *os_family*.

    Note there is no ``sec-ch-ua`` handling yet — client hints are emitted by
    the kernel, and keeping them in sync with ``ua_major`` is an M1 concern
    (``KernelAdapter.to_kernel_spec``).
    """
    ua_os = OS_PROFILES[os_family]["ua_os"]
    return (
        f"Mozilla/5.0 ({ua_os}) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{major}.0.0.0 Safari/537.36"
    )


def derive(
    seed: int,
    geo: GeoProfile,
    os_family: Optional[str] = None,
) -> Fingerprint:
    """Derive a fully self-consistent fingerprint from ``(seed, geo)``.

    The result is a pure function of its inputs: identical inputs produce an
    identical :class:`Fingerprint` on any machine and any Python version.
    Pass *os_family* to pin the OS instead of letting the seed choose it.

    Note that this function does **not** validate. Call
    :func:`proteus.fingerprint.consistency.check` and refuse to launch on any
    ``fatal`` violation.
    """
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an int")
    if seed < 0:
        raise ValueError("seed must be non-negative")
    if not isinstance(geo, GeoProfile):
        raise TypeError("geo must be a GeoProfile")

    if os_family is None:
        os_family = pick(seed, "os_family", OS_FAMILIES)
    if os_family not in OS_PROFILES:
        raise ValueError(
            f"unknown os_family {os_family!r}; known: {', '.join(OS_FAMILIES)}"
        )

    table = OS_PROFILES[os_family]
    major: int = pick(seed, "chrome_major", CHROME_MAJORS)
    width, height = pick(seed, "screen", table["screens"])

    # Canvas/audio noise must be seed-derived too. A per-session random
    # perturbation would break the "same profile looks like the same device"
    # promise, which is the whole point of the project.
    canvas_noise = index_of(seed, "canvas_noise", 256) - 128
    audio_noise = (index_of(seed, "audio_noise", 2001) - 1000) / 1e7

    return Fingerprint(
        seed=seed,
        geo=geo,
        os_family=os_family,
        platform=table["platform"],
        ua=build_ua(os_family, major),
        ua_major=major,
        screen_width=width,
        screen_height=height,
        device_pixel_ratio=float(pick(seed, "device_pixel_ratio", table["device_pixel_ratios"])),
        hardware_concurrency=int(pick(seed, "hardware_concurrency", table["hardware_concurrency"])),
        device_memory=int(pick(seed, "device_memory", table["device_memory"])),
        webgl_vendor=table["webgl_vendor"],
        webgl_renderer=pick(seed, "webgl_renderer", table["webgl_renderers"]),
        font_profile=table["font_profile"],
        canvas_noise=canvas_noise,
        audio_noise=audio_noise,
    )


def derive_for_country(
    seed: int,
    country: str,
    os_family: Optional[str] = None,
) -> Fingerprint:
    """Convenience wrapper: :func:`derive` using a built-in country geo sample."""
    return derive(seed=seed, geo=GeoProfile.for_country(country), os_family=os_family)
