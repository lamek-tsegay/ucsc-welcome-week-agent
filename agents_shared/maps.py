"""Google Maps deep links from the curated landmark coordinates.

A name like "East Upper Field" means nothing to someone who arrived on campus
yesterday. A link that opens the blue-dot map does. Landmarks carry
hand-estimated lat/lon (see data/landmarks.json _meta), which is exactly good
enough for a map pin and turn-by-turn from Google — and every message that
embeds one of these links carries the approximate-pin caveat, in keeping with
the honesty rules.

These are plain URL builders, no API key and no network call: the links open in
the student's own Google Maps app or browser.
"""

from __future__ import annotations

from agents_shared.loader import landmarks

PIN_CAVEAT = "_Map pins are approximate — my coordinates are hand-estimated._"


def _coords(landmark_id: str) -> tuple[float, float] | None:
    entry = landmarks().get(landmark_id)
    if not entry:
        return None
    lat, lon = entry.get("lat"), entry.get("lon")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    return float(lat), float(lon)


def pin_url(landmark_id: str) -> str | None:
    """A Google Maps pin for one landmark, or None if it has no coordinates."""
    coords = _coords(landmark_id)
    if coords is None:
        return None
    lat, lon = coords
    return f"https://www.google.com/maps/search/?api=1&query={lat:.5f}%2C{lon:.5f}"


def walking_url(origin_id: str, dest_id: str) -> str | None:
    """Google Maps turn-by-turn walking directions between two landmarks."""
    origin, dest = _coords(origin_id), _coords(dest_id)
    if origin is None or dest is None:
        return None
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={origin[0]:.5f}%2C{origin[1]:.5f}"
        f"&destination={dest[0]:.5f}%2C{dest[1]:.5f}"
        "&travelmode=walking"
    )


def pin_line(landmark_id: str, label: str = "Open in Google Maps") -> str | None:
    """A ready-made markdown line: 📍 [label](url)."""
    url = pin_url(landmark_id)
    return f"📍 [{label}]({url})" if url else None


def walking_line(
    origin_id: str, dest_id: str, label: str = "Open walking route in Google Maps"
) -> str | None:
    url = walking_url(origin_id, dest_id)
    return f"🧭 [{label}]({url})" if url else None
