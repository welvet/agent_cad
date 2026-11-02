# A dress-like tapered solid: wide below, narrow above.
root = loft([
    circle(30, at=(20, 20, 0)),
    circle(10, at=(20, 20, 35)),
])
root = root.hole(diameter=4, depth=12, at=(20, 20, 35))
