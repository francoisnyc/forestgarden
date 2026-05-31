"""Zoning district minimum lot size lookup."""

from typing import Optional


# Zones that have no residential use — return None
_NON_RESIDENTIAL_PREFIXES = ("M", "C", "PARK", "BPC")


def get_zoning_minimums(
    zone_dist: Optional[str], zoning_config: dict
) -> Optional[dict]:
    """Return {"area": float, "frontage": float} for a zoning district.

    Returns None if the zone doesn't allow residential use (M, C, PARK, etc.).
    Falls back to the "default" entry for unknown residential zones.
    """
    if not zone_dist:
        return dict(zoning_config["default"])

    zone_dist = zone_dist.strip().upper()

    for prefix in _NON_RESIDENTIAL_PREFIXES:
        if zone_dist.startswith(prefix):
            return None

    # Try exact match first
    if zone_dist in zoning_config:
        return dict(zoning_config[zone_dist])

    # Try stripping trailing letter variants (e.g., R6A → R6)
    base = zone_dist.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    if base and base in zoning_config:
        return dict(zoning_config[base])

    return dict(zoning_config["default"])
