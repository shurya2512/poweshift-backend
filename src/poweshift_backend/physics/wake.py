"""Bounded wake multiplier inside admitted interaction evidence."""


def wake_multiplier(gap_m: float, minimum_multiplier: float, support_distance_m: float) -> float:
    """Return a bounded linear wake effect inside source support."""
    if gap_m < 0.0 or not 0.0 < minimum_multiplier <= 1.0 or support_distance_m <= 0.0:
        raise ValueError("wake inputs are outside supported bounds")
    if gap_m >= support_distance_m:
        return 1.0
    return minimum_multiplier + (1.0 - minimum_multiplier) * gap_m / support_distance_m
