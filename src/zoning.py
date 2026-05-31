"""Zoning district minimum lot size lookup."""

_NON_RESIDENTIAL_PREFIXES = ("M", "C", "PARK", "BPC")


def get_zoning_minimums(zone_dist, zoning_config):
    if not zone_dist:
        return dict(zoning_config["default"])

    zone_dist = zone_dist.strip().upper()

    for prefix in _NON_RESIDENTIAL_PREFIXES:
        if zone_dist.startswith(prefix):
            return None

    if zone_dist in zoning_config:
        return dict(zoning_config[zone_dist])

    base = zone_dist.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    if base and base in zoning_config:
        return dict(zoning_config[base])

    return dict(zoning_config["default"])
