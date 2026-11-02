"""Small modeling vocabulary. Loaded only inside the FreeCAD worker."""
from __future__ import annotations

import math
import itertools
import FreeCAD as App
import Part


class ModelError(ValueError):
    pass


HISTORY = []


def number(value, name="value", positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelError(f"{name} must be a finite number in 0.1 increments")
    if not math.isfinite(value) or abs(value * 10 - round(value * 10)) > 1e-7:
        raise ModelError(f"{name}={value!r}: use 0.1 increments (one decimal place)")
    if positive and value <= 0:
        raise ModelError(f"{name} must be greater than zero")
    return float(value)


def vector(value, name="point"):
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ModelError(f"{name} must be an (x, y, z) tuple")
    return App.Vector(*(number(v, f"{name}[{i}]") for i, v in enumerate(value)))


def direction(axis):
    axes = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1),
            "-X": (-1, 0, 0), "-Y": (0, -1, 0), "-Z": (0, 0, -1)}
    try:
        return App.Vector(*axes[axis.upper().lstrip("+")])
    except (KeyError, AttributeError):
        raise ModelError("axis must be X, Y, Z, -X, -Y, or -Z") from None


def _valid(shape, operation):
    if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1 or shape.Volume <= 0:
        raise ModelError(f"{operation} must produce exactly one valid, connected solid")
    return shape


class Solid:
    """Immutable solid; tools never appear in the final exported object."""

    def __init__(self, shape, operation):
        self.shape = _valid(shape, operation)
        self.operation = operation
        self.index = len(HISTORY)
        HISTORY.append(self)

    def add(self, *tools):
        items = list(_tools(tools))
        if not items:
            raise ModelError("merge needs at least one tool")
        shape = self.shape.multiFuse([tool.shape for tool in items]).removeSplitter()
        return Solid(shape, "add")

    def merge(self, *tools):
        return self.add(*tools)

    def cut(self, *tools):
        shape = self.shape
        items = list(_tools(tools))
        if not items:
            raise ModelError("subtract needs at least one tool")
        for tool in items:
            cutter = _solid(tool).shape
            overlap = shape.common(cutter).Volume
            if overlap <= 1e-8:
                raise ModelError("cut tool does not remove any material")
            shape = shape.cut(cutter).removeSplitter()
        return Solid(shape, "cut")

    def subtract(self, *tools):
        return self.cut(*tools)

    def intersect(self, tool):
        return Solid(self.shape.common(_solid(tool).shape).removeSplitter(), "intersect")

    def move(self, delta):
        shape = self.shape.copy()
        shape.translate(vector(delta, "delta"))
        return Solid(shape, "move")

    def rotate(self, angle, axis="Z", at=(0, 0, 0)):
        shape = self.shape.copy()
        shape.rotate(vector(at), direction(axis), number(angle, "angle"))
        return Solid(shape, "rotate")

    def mirror(self, plane="YZ", at=(0, 0, 0)):
        normals = {"XY": "Z", "XZ": "Y", "YZ": "X"}
        if plane not in normals:
            raise ModelError("mirror plane must be XY, XZ, or YZ")
        return Solid(self.shape.mirror(vector(at), direction(normals[plane])), "mirror")

    def scale(self, factor, at=(0, 0, 0)):
        shape = self.shape.copy()
        shape.scale(number(factor, "factor", True), vector(at))
        return Solid(shape, "scale")

    def fillet(self, radius, edges="all"):
        return Solid(self.shape.makeFillet(number(radius, "radius", True), self._edges(edges)), "fillet")

    def chamfer(self, distance, edges="all"):
        return Solid(self.shape.makeChamfer(number(distance, "distance", True), self._edges(edges)), "chamfer")

    def hole(self, diameter, depth, at, axis="-Z"):
        return self.cut(cylinder(diameter, depth, at=at, axis=axis))

    def _edges(self, selection):
        edges = self.shape.Edges
        bounds = self.shape.optimalBoundingBox()
        if selection == "all":
            return edges
        if selection == "vertical":
            result = [e for e in edges if e.BoundBox.ZLength > 1e-7
                      and e.BoundBox.XLength < 1e-7 and e.BoundBox.YLength < 1e-7]
        elif selection in ("top", "bottom"):
            z = bounds.ZMax if selection == "top" else bounds.ZMin
            result = [e for e in edges if abs(e.BoundBox.ZMin-z) < 1e-7
                      and abs(e.BoundBox.ZMax-z) < 1e-7]
        elif isinstance(selection, (list, tuple)):
            result = []
            for label in selection:
                if not isinstance(label, str) or not label.startswith("E") or not label[1:].isdigit():
                    raise ModelError("edge IDs must look like E1, E2; use IDs from the latest result")
                index = int(label[1:]) - 1
                if index < 0 or index >= len(edges):
                    raise ModelError(f"unknown edge {label}")
                result.append(edges[index])
        else:
            raise ModelError("edges must be all, vertical, top, bottom, or a list of E IDs")
        if not result:
            raise ModelError(f"edge selection {selection!r} is empty")
        return result


def _solid(value):
    if not isinstance(value, Solid):
        raise ModelError("expected a solid from box/cylinder/extrude/loft/etc.")
    return value


def _tools(items):
    """Arrays are tool collections, not disconnected root solids."""
    for item in items:
        if isinstance(item, (list, tuple)):
            yield from _tools(item)
        else:
            yield _solid(item)


def _count(value, name="count"):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ModelError(f"{name} must be a positive integer")
    return value


def array(tool, count, step):
    """Copies including the original; count=int for linear, (nx,ny,nz) for grid."""
    tool = _solid(tool)
    delta = vector(step, "step")
    if isinstance(count, int) and not isinstance(count, bool):
        count = _count(count)
        if count > 1 and delta.Length < 1e-8:
            raise ModelError("array step must be nonzero when count > 1")
        if count > 1000:
            raise ModelError("array is limited to 1000 copies")
        shifts = [delta*i for i in range(count)]
    elif isinstance(count, (tuple, list)) and len(count) == 3:
        counts = [_count(n, f"count[{i}]") for i, n in enumerate(count)]
        if math.prod(counts) > 1000:
            raise ModelError("array is limited to 1000 copies")
        for n, distance in zip(counts, (delta.x, delta.y, delta.z)):
            if n > 1 and abs(distance) < 1e-8:
                raise ModelError("grid axes with more than one copy need a nonzero step")
        shifts = [App.Vector(delta.x*i, delta.y*j, delta.z*k)
                  for i, j, k in itertools.product(*(range(n) for n in counts))]
    else:
        raise ModelError("count must be a positive integer or (nx, ny, nz)")
    copies = []
    for delta in shifts:
        shape = tool.shape.copy()
        shape.translate(delta)
        copies.append(Solid(shape, "array copy"))
    return copies


def radial_array(tool, count, at=(0, 0, 0), axis="Z", angle=360):
    tool = _solid(tool)
    count = _count(count)
    span = number(angle, "angle", True)
    if span > 360:
        raise ModelError("radial array angle must be at most 360 degrees")
    if count > 1000:
        raise ModelError("array is limited to 1000 copies")
    origin, normal = vector(at), direction(axis)
    # Full circles do not duplicate the first copy at 360 degrees.
    divisions = count if span == 360 else max(1, count-1)
    copies = []
    for i in range(count):
        shape = tool.shape.copy()
        # Derived angles retain exact precision, e.g. seven evenly spaced holes.
        shape.rotate(origin, normal, span*i/divisions)
        copies.append(Solid(shape, "radial array copy"))
    return copies


def box(x, y, z, at=(0, 0, 0)):
    return Solid(Part.makeBox(number(x, "x", True), number(y, "y", True),
                              number(z, "z", True), vector(at)), "box")


def cylinder(diameter, height, at=(0, 0, 0), axis="Z"):
    return Solid(Part.makeCylinder(number(diameter, "diameter", True)/2,
                                  number(height, "height", True), vector(at), direction(axis)), "cylinder")


def cone(bottom_diameter, top_diameter, height, at=(0, 0, 0), axis="Z"):
    bottom = number(bottom_diameter, "bottom_diameter")
    top = number(top_diameter, "top_diameter")
    if min(bottom, top) < 0 or max(bottom, top) == 0:
        raise ModelError("cone diameters must be nonnegative and at least one positive")
    if bottom == top:
        return cylinder(bottom, height, at, axis)
    return Solid(Part.makeCone(bottom/2, top/2, number(height, "height", True),
                              vector(at), direction(axis)), "cone")


def sphere(diameter, at=(0, 0, 0)):
    return Solid(Part.makeSphere(number(diameter, "diameter", True)/2, vector(at)), "sphere")


def tube(outer_diameter, wall, height, at=(0, 0, 0), axis="Z"):
    outer = number(outer_diameter, "outer_diameter", True)
    thickness = number(wall, "wall", True)
    if thickness * 2 >= outer:
        raise ModelError("tube wall must be less than half its outer diameter")
    return cylinder(outer, height, at, axis).cut(cylinder(round(outer-2*thickness, 1), height, at, axis))


class Profile:
    def __init__(self, wire):
        if not wire.isClosed():
            raise ModelError("profile must be closed")
        face = Part.Face(wire)
        if not face.isValid() or face.Area <= 1e-8:
            raise ModelError("profile must be planar, valid, and have positive area")
        self.wire = wire

    def offset(self, distance, corners="round"):
        amount = number(distance, "distance")
        joins = {"round": 0, "sharp": 2}
        if corners not in joins:
            raise ModelError("offset corners must be round or sharp")
        if amount == 0:
            return Profile(self.wire.copy())
        result = self.wire.makeOffset2D(amount, join=joins[corners])
        if len(result.Wires) != 1:
            raise ModelError("offset must produce one closed outline; reduce the distance")
        return Profile(result.Wires[0])


class Path:
    def __init__(self, wire):
        self.wire = wire


def _place(wire, at, plane):
    # local coordinates: XY=(x,y), XZ=(x,z), YZ=(y,z)
    if plane == "XZ":
        wire.rotate(App.Vector(), App.Vector(1, 0, 0), 90)
    elif plane == "YZ":
        wire.rotate(App.Vector(), App.Vector(0, 0, 1), 90)
        wire.rotate(App.Vector(), App.Vector(0, 1, 0), 90)
    elif plane != "XY":
        raise ModelError("plane must be XY, XZ, or YZ")
    wire.translate(vector(at))
    return Profile(wire)


def circle(diameter, at=(0, 0, 0), plane="XY"):
    edge = Part.makeCircle(number(diameter, "diameter", True)/2)
    return _place(Part.Wire([edge]), at, plane)


def rectangle(width, height, at=(0, 0, 0), plane="XY"):
    w, h = number(width, "width", True), number(height, "height", True)
    return polygon([(0, 0), (w, 0), (w, h), (0, h)], at, plane)


def polygon(points, at=(0, 0, 0), plane="XY"):
    if len(points) < 3:
        raise ModelError("polygon needs at least three 2D points")
    vertices = []
    for p in points:
        if len(p) != 2:
            raise ModelError("polygon points are (u, v) pairs; use at and plane for placement")
        vertices.append(App.Vector(number(p[0], "u"), number(p[1], "v"), 0))
    if (vertices[-1]-vertices[0]).Length > 1e-7:
        vertices.append(vertices[0])
    return _place(Part.makePolygon(vertices), at, plane)


def line(start, end):
    return Path(Part.Wire([Part.makeLine(vector(start), vector(end))]))


def polyline(points, closed=False):
    if len(points) < (3 if closed else 2):
        raise ModelError("polyline needs at least two points, or three for a closed profile")
    vertices = [vector(p) for p in points]
    if closed and (vertices[-1]-vertices[0]).Length > 1e-7:
        vertices.append(vertices[0])
    result = Part.makePolygon(vertices)
    return Profile(result) if closed else Path(result)


def arc(start, through, end):
    return Path(Part.Wire([Part.Arc(vector(start), vector(through), vector(end)).toShape()]))


def curve(points, closed=False):
    if len(points) < 3:
        raise ModelError("curve needs at least three 3D points")
    spline = Part.BSplineCurve()
    spline.interpolate([vector(p) for p in points], PeriodicFlag=bool(closed))
    wire = Part.Wire([spline.toShape()])
    return Profile(wire) if closed else Path(wire)


def spline(points, closed=False):
    return curve(points, closed)


def wire(*segments, closed=False):
    edges = []
    for segment in segments:
        if not isinstance(segment, (Path, Profile)):
            raise ModelError("wire segments must be line/arc/curve results")
        edges.extend(segment.wire.Edges)
    if not edges:
        raise ModelError("wire needs at least one segment")
    joined = Part.Wire(edges)
    if not joined.isValid():
        raise ModelError("wire segments must connect in order")
    return Profile(joined) if closed else Path(joined)


def extrude(profile, height, axis="Z"):
    if not isinstance(profile, Profile):
        raise ModelError("extrude requires a closed profile")
    return Solid(Part.Face(profile.wire).extrude(direction(axis)*number(height, "height", True)), "extrude")


def loft(profiles, ruled=False):
    if len(profiles) < 2 or not all(isinstance(p, Profile) for p in profiles):
        raise ModelError("loft needs at least two closed profiles at different positions")
    return Solid(Part.makeLoft([p.wire for p in profiles], True, bool(ruled)), "loft")


def revolve(profile, angle=360, axis="Z", at=(0, 0, 0)):
    if not isinstance(profile, Profile):
        raise ModelError("revolve requires a closed profile")
    amount = number(angle, "angle", True)
    if amount > 360:
        raise ModelError("revolve angle must be at most 360 degrees")
    return Solid(Part.Face(profile.wire).revolve(vector(at), direction(axis), amount), "revolve")


def sweep(profile, path):
    if not isinstance(profile, Profile) or not isinstance(path, Path):
        raise ModelError("sweep needs a closed profile and a line/arc/curve/wire path")
    return Solid(path.wire.makePipeShell([profile.wire], True, False), "sweep")


def pipe(diameter, path, wall=None):
    """Circular sweep: infer the profile position and normal from the path."""
    if not isinstance(path, Path):
        raise ModelError("pipe path must be a line, arc, spline, polyline, or open wire")
    outer = number(diameter, "diameter", True)
    thickness = None if wall is None else number(wall, "wall", True)
    if thickness is not None and 2*thickness >= outer:
        raise ModelError("pipe wall must be less than half its diameter")
    edge = path.wire.OrderedEdges[0]
    reverse = edge.Orientation == "Reversed"
    parameter = edge.LastParameter if reverse else edge.FirstParameter
    origin = edge.valueAt(parameter)
    tangent = edge.tangentAt(parameter)
    if reverse:
        tangent = -tangent
    def section(radius):
        return Profile(Part.Wire([Part.makeCircle(radius, origin, tangent)]))
    outer_solid = sweep(section(outer/2), path)
    if thickness is None:
        return outer_solid
    return outer_solid.cut(sweep(section(outer/2-thickness), path))


PUBLIC = {name: globals()[name] for name in (
    "box", "cylinder", "cone", "sphere", "tube", "circle", "rectangle", "polygon",
    "line", "arc", "curve", "spline", "polyline", "wire", "extrude", "loft", "revolve", "sweep",
    "array", "radial_array", "pipe",
)}
