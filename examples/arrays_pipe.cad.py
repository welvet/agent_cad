# One solid: rounded plate, curved hollow pipe, and a radial bolt pattern.
root = box(60, 40, 4).fillet(1.5, edges="vertical")

route = spline([(10, 10, 2), (10, 10, 16), (24, 10, 25), (38, 10, 16)])
root = root.merge(pipe(6, route, wall=1))

bolt = cylinder(3, 6, at=(42, 20, 5), axis="-Z")
bolts = radial_array(bolt, count=4, at=(30, 20, 0))
root = root.subtract(bolts)
