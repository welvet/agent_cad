# A 10 mm cube, rounded outside edges, and a centered 2 mm blind hole.
root = box(10, 10, 10)
root = root.fillet(0.5)
root = root.hole(diameter=2, depth=5, at=(5, 5, 10))
