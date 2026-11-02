"""Generic surface-color sampling and OBJ+MTL writing; no model-specific rules."""
from collections import Counter
import math
from pathlib import Path
import re
import runpy

EPS = 1e-8


def load_colors(path):
    namespace = runpy.run_path(str(path))
    raw = namespace.get("PALETTE")
    if not isinstance(raw, dict) or not raw:
        raise ValueError("colors.py must define a nonempty PALETTE dict")
    palette = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
            raise ValueError("material names must start with a letter and use letters, digits, underscores")
        if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            rgb = tuple(int(value[i:i+2],16)/255 for i in (1,3,5))
        elif isinstance(value, (tuple,list)) and len(value) == 3:
            rgb = tuple(float(c) for c in value)
        else:
            raise ValueError(f"invalid color for {name}: use #RRGGBB or three RGB numbers in 0..1")
        if not all(math.isfinite(c) and 0 <= c <= 1 for c in rgb):
            raise ValueError(f"RGB values for {name} must be finite and in 0..1")
        palette[name] = rgb
    callback = namespace.get("color_at")
    if not callable(callback):
        if len(palette) != 1:
            raise ValueError("define color_at(x,y,z) returning one PALETTE key")
        callback = lambda x,y,z: next(iter(palette))
    raw_planes = namespace.get("SPLIT_PLANES", {})
    if not isinstance(raw_planes, dict) or any(k not in ("x","y","z") for k in raw_planes):
        raise ValueError("SPLIT_PLANES must map x/y/z to lists of plane positions in mm")
    planes = []
    for axis, values in raw_planes.items():
        if not isinstance(values, (list,tuple)):
            raise ValueError("split plane positions must be a list")
        for value in values:
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                raise ValueError("split plane positions must be finite numbers")
            if abs(value*10-round(value*10)) > 1e-7:
                raise ValueError("split plane positions must use 0.1 mm increments")
            planes.append(("xyz".index(axis), float(value)))
    planes = sorted(set(planes))
    if len(planes) > 128:
        raise ValueError("use at most 128 split planes; avoid unnecessarily dense paint grids")
    def color(point):
        key = callback(*point)
        if not isinstance(key,str) or key not in palette:
            raise ValueError(f"color_at returned unknown material {key!r} at {tuple(round(v,3) for v in point)}")
        return key
    return palette, color, planes


def half(poly, axis, value, positive):
    result = []
    for a,b in zip(poly,poly[1:]+poly[:1]):
        da,db = a[axis]-value,b[axis]-value
        inside = da >= -EPS if positive else da <= EPS
        other = db >= -EPS if positive else db <= EPS
        if inside:
            result.append(a)
        if inside != other:
            t = da/(da-db)
            result.append(tuple(a[j]+t*(b[j]-a[j]) for j in range(3)))
    cleaned = []
    for point in result:
        if not cleaned or sum((a-b)**2 for a,b in zip(point,cleaned[-1])) > 1e-18:
            cleaned.append(point)
    if len(cleaned)>1 and sum((a-b)**2 for a,b in zip(cleaned[0],cleaned[-1])) < 1e-18:
        cleaned.pop()
    return cleaned


def colored_mesh(shape, palette, color_at, planes, deflection=0.02):
    points, triangles = shape.tessellate(deflection)
    points = [(v.x,v.y,v.z) for v in points]
    vertices, lookup = [], {}
    groups = {name:[] for name in palette}
    edge_counts = Counter()
    base_edges = Counter()
    for tri in triangles:
        for a,b in zip(tri,tri[1:]+tri[:1]):
            base_edges[tuple(sorted((a,b)))] += 1
    def index(point):
        key = tuple(round(v,6) for v in point)
        if key not in lookup:
            lookup[key] = len(vertices)+1
            vertices.append(key)
        return lookup[key]
    for tri in triangles:
        original = [points[i] for i in tri]
        polygons = [original]
        for axis,value in planes:
            if not min(p[axis] for p in original)+EPS < value < max(p[axis] for p in original)-EPS:
                continue
            split = []
            for poly in polygons:
                if min(p[axis] for p in poly)+EPS < value < max(p[axis] for p in poly)-EPS:
                    split.extend(p for p in (half(poly,axis,value,False),half(poly,axis,value,True)) if len(p)>=3)
                else:
                    split.append(poly)
            polygons = split
        for poly in polygons:
            for i in range(1,len(poly)-1):
                triangle = [poly[0],poly[i],poly[i+1]]
                ids = tuple(index(p) for p in triangle)
                if len(set(ids)) < 3:
                    continue
                centroid = tuple(sum(p[j] for p in triangle)/3 for j in range(3))
                groups[color_at(centroid)].append(ids)
                for a,b in zip(ids,ids[1:]+ids[:1]):
                    edge_counts[tuple(sorted((a,b)))] += 1
    if not vertices:
        raise ValueError("CAD tessellation produced no mesh")
    bounds = [[min(p[i] for p in vertices),max(p[i] for p in vertices)] for i in range(3)]
    stats = {"vertices":len(vertices), "triangles":sum(map(len,groups.values())),
             "material_triangles":{k:len(v) for k,v in groups.items()},
             "source_mesh_edge_anomalies":sum(n != 2 for n in base_edges.values()),
             "mesh_edge_anomalies":sum(n != 2 for n in edge_counts.values()),
             "size_mm":[round(b-a,3) for a,b in bounds]}
    return vertices,groups,stats


def write_obj(output, vertices, groups, palette):
    output = Path(output)
    obj,mtl = output/"model.obj",output/"model.mtl"
    with mtl.open("w",encoding="utf-8",newline="\n") as file:
        for name,rgb in palette.items():
            file.write(f"newmtl {name}\nKd {' '.join(f'{c:.6f}' for c in rgb)}\nKa 0.1 0.1 0.1\nKs 0 0 0\nd 1\nillum 1\n\n")
    with obj.open("w",encoding="utf-8",newline="\n") as file:
        file.write("# Units: millimeters. Z up. Named material surface colors.\nmtllib model.mtl\no Model\ns off\n")
        for point in vertices:
            file.write("v "+" ".join(f"{v:.6f}" for v in point)+"\n")
        for name,faces in groups.items():
            if faces:
                file.write(f"usemtl {name}\n")
                for face in faces:
                    file.write("f "+" ".join(map(str,face))+"\n")
    return obj,mtl
