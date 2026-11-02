"""Runs inside FreeCAD GUI. Reloads Root while preserving the user's camera."""
import hashlib
import json
from pathlib import Path
import time
import re
import math

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from project import atomic_json

SESSIONS = {}


def same_camera(before, after):
    # Inventor serializes floats with slightly different precision on round-trip.
    def fields(text):
        result = {}
        for key in ("position", "orientation", "height", "heightAngle", "focalDistance"):
            match = re.search(r"\b"+key+r"\s+([-+0-9.eE ]+)", text)
            if match:
                result[key] = [float(v) for v in match.group(1).split()]
        return result
    a, b = fields(before), fields(after)
    return a.keys() == b.keys() and all(len(a[k]) == len(b[k]) and all(
        math.isclose(x, y, rel_tol=1e-5, abs_tol=1e-5) for x, y in zip(a[k], b[k])) for k in a)


class ReviewSession:
    def __init__(self, project):
        self.project = Path(project)
        self.revision = None
        self.doc = None
        self.doc_name = None
        self.geometry_hash = None
        self.camera_preserved = None
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(750)
        self.tick()

    def capture(self):
        try:
            if self.doc is not None:
                Gui.getMainWindow().show()
                Gui.getDocument(self.doc.Name).activeView().redraw()
                Gui.updateGui()
                Gui.getDocument(self.doc.Name).activeView().saveImage(
                    str(self.project/"previews"/"live_view.png"), 1024, 768, "Current")
        except Exception as exc:
            App.Console.PrintWarning(f"Live preview capture: {exc}\n")

    def tick(self):
        state = "waiting"
        try:
            manifest = json.loads((self.project/"project.json").read_text(encoding="utf-8"))
            if (self.project/"live_stop").exists():
                self.timer.stop()
                self.status("stopped", manifest)
                return
            if self.doc_name is not None and self.doc_name not in App.listDocuments():
                self.timer.stop()
                atomic_json(self.project/"live_status.json", {"state": "closed", "heartbeat": 0})
                return
            if self.revision != manifest["revision"]:
                if self.doc is not None:
                    root = self.doc.getObject("Root")
                    current = hashlib.sha256(root.Shape.exportBrepToString().encode()).hexdigest()
                    if current != self.geometry_hash:
                        state = "paused_user_geometry_changed"
                        self.status(state, manifest)
                        return
                saved = App.openDocument(manifest["freecad"], hidden=True)
                try:
                    source_root = saved.getObject("Root")
                    if self.doc is None:
                        self.doc = App.newDocument("AgentReview")
                        self.doc_name = self.doc.Name
                        self.doc.Label = self.project.name+" — live review"
                        self.doc.addObject("Part::Feature", "Root")
                        first = True
                    else:
                        first = False
                    App.setActiveDocument(self.doc.Name)
                    view = Gui.activeDocument().activeView()
                    camera = None if first else view.getCamera()
                    root = self.doc.getObject("Root")
                    root.Shape = source_root.Shape.copy()
                    for name in ("SourcePath", "SourceSHA256", "ModelScript"):
                        if name not in root.PropertiesList:
                            root.addProperty("App::PropertyString", name, "Model")
                        setattr(root, name, getattr(source_root, name))
                    root.ViewObject.ShapeColor = (0.45, 0.68, 0.84)
                    root.ViewObject.LineColor = (0.12, 0.20, 0.27)
                    root.ViewObject.DisplayMode = "Flat Lines"
                    root.ViewObject.Visibility = True
                    self.doc.recompute()
                    # The headless worker owns model.FCStd. Save a separate native
                    # review session to avoid racing or overwriting user edits.
                    self.doc.saveAs(str(self.project/"history"/"live_review.FCStd"))
                    if first:
                        view.viewAxonometric()
                        view.fitAll()
                    else:
                        view.setCamera(camera)
                    self.camera_preserved = None if first else same_camera(camera, view.getCamera())
                    self.geometry_hash = hashlib.sha256(root.Shape.exportBrepToString().encode()).hexdigest()
                    self.revision = manifest["revision"]
                    QtCore.QTimer.singleShot(1000, self.capture)
                finally:
                    App.closeDocument(saved.Name)
                    if self.doc is not None:
                        App.setActiveDocument(self.doc.Name)
                state = "updated"
            else:
                state = "watching"
            self.status(state, manifest)
        except Exception as exc:
            atomic_json(self.project/"live_status.json", {"state": "error", "error": str(exc), "heartbeat": time.time()})

    def status(self, state, manifest):
        atomic_json(self.project/"live_status.json", {"state": state, "heartbeat": time.time(),
                   "revision": self.revision, "target_revision": manifest["revision"],
                   "camera_preserved": self.camera_preserved,
                   "document": self.doc.Name if self.doc else None})


def start(project):
    key = str(Path(project).resolve())
    if key not in SESSIONS:
        SESSIONS[key] = ReviewSession(key)
