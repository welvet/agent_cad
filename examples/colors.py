"""Example color rules for the 10 mm cube. Coordinates are global millimeters."""
PALETTE = {"Blue": "#085BB5", "Silver": "#C3C8CD", "Red": "#D32632"}
SPLIT_PLANES = {"z": [3, 7]}


def color_at(x, y, z):
    if z < 3:
        return "Blue"
    if z < 7:
        return "Silver"
    return "Red"
