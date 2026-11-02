"""Headless z-buffer previews from in-memory FreeCAD tessellation. No STL files."""
from pathlib import Path
import math
import itertools
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont


VIEWS = {
    "top": ((0, 0, 1), (0, 1, 0), "X right / Y up"),
    "front": ((0, -1, 0), (0, 0, 1), "X right / Z up"),
    "right": ((1, 0, 0), (0, 0, 1), "Y right / Z up"),
    "isometric": ((1, -1, 1), (0, 0, 1), "+X / -Y / +Z"),
}


def font(size):
    try:
        return ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", size)
    except OSError:
        return ImageFont.load_default()


def validate_options(size=1024, views=None, region=None):
    if isinstance(size, bool) or not isinstance(size, int) or not 256 <= size <= 2048:
        raise ValueError("resolution must be an integer from 256 to 2048")
    names = list(VIEWS) if views is None else list(views)
    if not names or any(name not in VIEWS for name in names):
        raise ValueError("view must be top, front, right, or isometric")
    corners = None
    if region is not None:
        try:
            bounds = np.asarray(region, dtype=float)
        except (TypeError, ValueError):
            raise ValueError("region must be [[xmin,ymin,zmin],[xmax,ymax,zmax]]") from None
        if bounds.shape != (2, 3) or not np.isfinite(bounds).all() or not (bounds[1] > bounds[0]).all():
            raise ValueError("region needs two finite XYZ corners with min < max on every axis")
        if not np.allclose(bounds*10, np.round(bounds*10), atol=1e-7, rtol=0):
            raise ValueError("region coordinates must use 0.1 mm increments")
        corners = np.array(list(itertools.product(*zip(bounds[0], bounds[1]))))
    return names, corners


def view_frame(points, basis, size):
    """Fit this camera's projected geometry, not the global longest dimension."""
    projected = points @ basis
    low, high = projected[:, :2].min(axis=0), projected[:, :2].max(axis=0)
    span = np.maximum(high-low, 1e-6)
    margin, header, footer = size*0.05, 76, 44
    available = np.array([size-2*margin, size-header-footer])
    scale = float(np.min(available/span))
    midpoint = (low+high)/2
    anchor = np.array([size/2, header+available[1]/2])
    return scale, midpoint, anchor, span*scale


def render_views(shape, output, size=1024, views=None, region=None):
    output = Path(output)
    names, focus_points = validate_options(size, views, region)
    vertices, faces = shape.tessellate(0.02)
    vertices = np.array([[v.x, v.y, v.z] for v in vertices], dtype=float)
    triangles = np.asarray(faces, dtype=int)
    if not len(triangles):
        raise ValueError("CAD tessellation returned no triangles")
    bounds = shape.optimalBoundingBox()
    edge_points = []
    for edge in shape.Edges:
        try:
            points = edge.discretize(Deflection=0.005)
        except Exception:
            points = edge.discretize(Number=64)
        edge_points.append(np.array([[v.x, v.y, v.z] for v in points]))
    images, paths, framing = [], {}, {}
    for name in names:
        eye, upward, caption = VIEWS[name]
        forward = np.asarray(eye, dtype=float)
        forward /= np.linalg.norm(forward)
        right = np.cross(np.asarray(upward), forward)
        right /= np.linalg.norm(right)
        up = np.cross(forward, right)
        basis = np.array([right, up, forward]).T
        scale, midpoint, anchor, span_pixels = view_frame(
            vertices if focus_points is None else focus_points, basis, size)
        framing[name] = {"resolution": size, "fit": "region" if region is not None else "independent",
                         "mm_per_pixel": round(1/scale, 6),
                         "projected_span_pixels": [round(float(v), 1) for v in span_pixels],
                         "region_mm": region}

        def project(points):
            p = points @ basis
            p[:, 0] = (p[:, 0]-midpoint[0])*scale + anchor[0]
            p[:, 1] = -(p[:, 1]-midpoint[1])*scale + anchor[1]
            return p

        projected = project(vertices)
        depth = np.full((size, size), -np.inf)
        pixels = np.full((size, size, 3), (245, 247, 250), dtype=np.uint8)
        light = np.array([-0.35, 0.55, 0.76])
        light /= np.linalg.norm(light)
        for tri in triangles:
            p = projected[tri]
            x0 = max(0, math.floor(p[:, 0].min()))
            x1 = min(size-1, math.ceil(p[:, 0].max()))
            y0 = max(0, math.floor(p[:, 1].min()))
            y1 = min(size-1, math.ceil(p[:, 1].max()))
            denom = ((p[1, 1]-p[2, 1])*(p[0, 0]-p[2, 0])
                     + (p[2, 0]-p[1, 0])*(p[0, 1]-p[2, 1]))
            if abs(denom) < 1e-9 or x0 > x1 or y0 > y1:
                continue
            xs, ys = np.meshgrid(np.arange(x0, x1+1)+0.5, np.arange(y0, y1+1)+0.5)
            a = ((p[1, 1]-p[2, 1])*(xs-p[2, 0])+(p[2, 0]-p[1, 0])*(ys-p[2, 1]))/denom
            b = ((p[2, 1]-p[0, 1])*(xs-p[2, 0])+(p[0, 0]-p[2, 0])*(ys-p[2, 1]))/denom
            c = 1-a-b
            z = a*p[0, 2]+b*p[1, 2]+c*p[2, 2]
            depth_region = depth[y0:y1+1, x0:x1+1]
            mask = (a >= -1e-7) & (b >= -1e-7) & (c >= -1e-7) & (z > depth_region)
            if not mask.any():
                continue
            world = vertices[tri]
            normal = np.cross(world[1]-world[0], world[2]-world[0])
            length = np.linalg.norm(normal)
            if length < 1e-12:
                continue
            normal = normal/length @ basis
            if normal[2] < 0:
                normal = -normal
            shade = 0.62 + 0.38*max(0, np.dot(normal, light))
            color = np.clip(np.array([111, 174, 217])*shade, 0, 255).astype(np.uint8)
            depth_region[mask] = z[mask]
            pixels[y0:y1+1, x0:x1+1][mask] = color

        # Draw only visible portions of actual CAD edges (not tessellation edges).
        for points in edge_points:
            projected_edge = project(points)
            for a, b in zip(projected_edge[:-1], projected_edge[1:]):
                # Clip edge sampling to the viewport; tiny close-ups must not
                # generate millions of samples for long off-screen edges.
                start, stop = 0.0, 1.0
                delta = b-a
                for axis in (0, 1):
                    if abs(delta[axis]) < 1e-12:
                        if a[axis] < 0 or a[axis] >= size:
                            stop = -1
                            break
                    else:
                        t0, t1 = sorted(((0-a[axis])/delta[axis], (size-1-a[axis])/delta[axis]))
                        start, stop = max(start, t0), min(stop, t1)
                if start > stop:
                    continue
                a, b = a+start*delta, a+stop*delta
                count = max(2, int(np.linalg.norm(b[:2]-a[:2])*2)+1)
                samples = np.linspace(a, b, count)
                for sample in samples:
                    x, y = int(sample[0]), int(sample[1])
                    if 0 <= x < size and 0 <= y < size:
                        patch = depth[max(0,y-1):min(size,y+2), max(0,x-1):min(size,x+2)]
                        finite = patch[np.isfinite(patch)]
                        if len(finite) and sample[2] >= finite.max()-max(0.06, 1.5/scale):
                            pixels[y, x] = (35, 65, 85)
        image = Image.fromarray(pixels)
        draw = ImageDraw.Draw(image)
        # Cropped geometry can extend past the target region; reserve label bars.
        draw.rectangle((0, 0, size, 67), fill=(245, 247, 250))
        draw.rectangle((0, size-36, size, size), fill=(245, 247, 250))
        draw.text((20, 14), name.upper(), fill=(25, 41, 59), font=font(21))
        draw.text((20, 43), caption + (" / CLOSE-UP" if region is not None else " / FIT TO VIEW"),
                  fill=(88, 103, 122), font=font(13))
        draw.text((20, size-30), f"{bounds.XLength:.1f} x {bounds.YLength:.1f} x {bounds.ZLength:.1f} mm",
                  fill=(60, 79, 97), font=font(14))
        path = output / f"{name}.png"
        image.save(path)
        paths[name] = str(path)
        images.append(image)
    # The contact sheet is only an overview. MCP returns the full-size images.
    thumbnail_size = min(size, 512)
    columns = 2 if len(images) > 1 else 1
    rows = math.ceil(len(images)/columns)
    sheet = Image.new("RGB", (thumbnail_size*columns, thumbnail_size*rows), "white")
    for i, image in enumerate(images):
        thumbnail = image.resize((thumbnail_size, thumbnail_size), Image.Resampling.LANCZOS)
        sheet.paste(thumbnail, ((i % columns)*thumbnail_size, (i // columns)*thumbnail_size))
    sheet.save(output / "views.png")
    (output/"framing.json").write_text(json.dumps(framing, indent=2), encoding="utf-8")
    return paths
