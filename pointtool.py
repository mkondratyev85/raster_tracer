from qgis.core import QgsPointXY, QgsPoint, QgsGeometry, QgsFeature, \
                      QgsVectorLayer, QgsProject, QgsWkbTypes, QgsApplication
from qgis.gui import QgsMapToolEmitPoint, QgsMapToolEdit, \
                     QgsRubberBand, QgsVertexMarker, QgsMapTool
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import Qgis

import numpy as np


from .astar import find_path, FindPathTask
from .line_simplification import smooth, simplify
from .utils import get_whole_raster, PossiblyIndexedImageError


class OutsideMapError(Exception):
    pass


class PointTool(QgsMapToolEdit):

    def deactivate(self):
        QgsMapTool.deactivate(self)
        self.deactivated.emit()

    def __init__(self, canvas, iface, turn_off_snap, smooth=False):
        self.last_mouse_event_pos = None
        self.iface = iface
        self.anchor_points = []
        self.anchor_points_ij = []
        self.is_tracing = True
        self.turn_off_snap = turn_off_snap
        self.smooth_line = smooth

        # possible variants: gray_diff, as_is, color_diff (using v from hsv)
        self.grid_conversion = "gray_diff"

        # QApplication.restoreOverrideCursor()
        # QApplication.setOverrideCursor(Qt.CrossCursor)
        QgsMapToolEmitPoint.__init__(self, canvas)

        self.rlayer = None
        self.grid_changed = None
        self.snap_tolerance = None
        self.vlayer = None
        self.grid = None
        self.sample = None

        self.tracking_is_active = False

        # False = not a polygon
        self.rubber_band = QgsRubberBand(self.canvas(), False)
        self.markers = []
        self.marker_snap = QgsVertexMarker(self.canvas())
        self.marker_snap.setColor(QColor(255, 0, 255))

        globals()['find_path_task'] = None

    def snap_tolerance_changed(self, snap_tolerance):
        self.snap_tolerance = snap_tolerance
        if snap_tolerance is None:
            self.marker_snap.hide()
        else:
            self.marker_snap.show()

    def trace_color_changed(self, color):
        r, g, b = self.sample

        if color is False:
            self.grid_changed = None
        else:
            r0, g0, b0, t = color.getRgb()
            self.grid_changed = np.abs((r0 - r) ** 2 + (g0 - g) ** 2 +
                                       (b0 - b) ** 2)

    def get_current_vector_layer(self):
        try:
            vlayer = self.iface.layerTreeView().selectedLayers()[0]
            if isinstance(vlayer, QgsVectorLayer):
                if  vlayer.wkbType() == QgsWkbTypes.MultiLineString:
                    return vlayer
                else:
                    self.iface.messageBar().pushMessage("The active" +
                                   " layer must be a MultiLineString vector layer",
                                          level=Qgis.Warning, duration=2)
                    return None
     
            else:
                self.iface.messageBar().pushMessage("Missing Layer",
                               "Please select vector layer to draw",
                                      level=Qgis.Warning, duration=2)
                return None
        except IndexError:
            self.iface.messageBar().pushMessage("Missing Layer",
                           "Please select vector layer to draw",
                                  level=Qgis.Warning, duration=2)
            return None

    def raster_layer_has_changed(self, raster_layer):
        self.rlayer = raster_layer
        if self.rlayer is None:
            self.iface.messageBar().pushMessage("Missing Layer",
                          "Please select raster layer to trace",
                                  level=Qgis.Warning, duration=2)
            return

        try:
            sample, to_indexes, to_coords, to_coords_provider, \
                to_coords_provider2 = \
                get_whole_raster(self.rlayer, QgsProject.instance())
        except PossiblyIndexedImageError:
            self.iface.messageBar().pushMessage("Missing Layer",
                            "Can't trace indexed or gray image",
                            level=Qgis.Critical, duration=2)
            return

        r = sample[0].astype(float)
        g = sample[1].astype(float)
        b = sample[2].astype(float)
        where_are_NaNs = np.isnan(r)
        r[where_are_NaNs] = 0
        where_are_NaNs = np.isnan(g)
        g[where_are_NaNs] = 0
        where_are_NaNs = np.isnan(b)
        b[where_are_NaNs] = 0

        self.sample = (r, g, b)
        self.grid = r + g + b
        self.to_indexes = to_indexes
        self.to_coords = to_coords
        self.to_coords_provider = to_coords_provider
        self.to_coords_provider2 = to_coords_provider2

    def keyPressEvent(self, e):
        # delete last segment if backspace is pressed
        if e.key() == Qt.Key_Backspace or e.key() == Qt.Key_B:
            # check if we have at least one feature to delete
            vlayer = self.get_current_vector_layer()
            if vlayer is None:
                return
            if vlayer.featureCount() < 1:
                return

            # it's a very ugly way of triggering single undo event
            self.iface.editMenu().actions()[0].trigger()

            # remove last marker
            if len(self.markers) > 0:
                last_marker = self.markers.pop()
                self.canvas().scene().removeItem(last_marker)

            # remove last anchor
            if len(self.anchor_points) > 0:
                self.anchor_points.pop()
                self.anchor_points_ij.pop()

            self.update_rubber_band()
            self.redraw()

        elif e.key() == Qt.Key_A:
            self.is_tracing = not self.is_tracing
            self.update_rubber_band()
        elif e.key() == Qt.Key_S:
            self.turn_off_snap()
        elif e.key() == Qt.Key_Escape:
            self.abort_tracing_process()

    def snap(self, i, j):
        if self.snap_tolerance is None:
            return i, j
        if not self.is_tracing:
            return i, j
        if self.grid_changed is None:
            return i, j

        size_i, size_j = self.grid.shape
        size = self.snap_tolerance

        if i < size or j < size or i + size > size_i or j + size > size_j:
            raise OutsideMapError

        grid_small = self.grid_changed
        grid_small = grid_small[i - size: i + size, j - size: j + size]

        smallest_cells = np.where(grid_small == np.amin(grid_small))
        coordinates = list(zip(smallest_cells[0], smallest_cells[1]))

        if len(coordinates) == 1:
            delta_i, delta_j = coordinates[0]
            delta_i -= size
            delta_j -= size
        else:
            # find the closest to the center
            deltas = [(i - size, j - size) for i, j in coordinates]
            lengths = [(i ** 2 + j ** 2) for i, j in deltas]
            i = lengths.index(min(lengths))
            delta_i, delta_j = deltas[i]

        return i+delta_i, j+delta_j

    def canvasReleaseEvent(self, mouseEvent):
        vlayer = self.get_current_vector_layer()
        if vlayer is None:
            return

        if not vlayer.isEditable():
            self.iface.messageBar().pushMessage("Edit mode",
                    "Please begin editing vector layer to trace",
                    level=Qgis.Warning, duration=2)
            return

        if self.rlayer is None:
            self.iface.messageBar().pushMessage("Missing Layer",
                                                "Please select raster layer to trace",
                                                level=Qgis.Warning, duration=2)

        self.last_mouse_event_pos = mouseEvent.pos()
        # hide rubber_band
        self.rubber_band.hide()

        # check if he haven't any new tasks yet
        if self.tracking_is_active:
            self.iface.messageBar().pushMessage(" ", 
                    "Please wait till the last segment is finished or terminate tracing by hitting Esc", 
                    level=Qgis.Critical, duration=1)
            return

        if (mouseEvent.button() == Qt.RightButton):
            # finish point path if it was last point
            self.anchor_points = []

            # hide all markers
            while len(self.markers) > 0:
                marker = self.markers.pop()
                self.canvas().scene().removeItem(marker)
            return

        qgsPoint = self.toMapCoordinates(mouseEvent.pos())
        x1, y1 = qgsPoint.x(), qgsPoint.y()

        if self.to_indexes is None:
            self.iface.messageBar().pushMessage("Missing Layer", 
                    "Please select correct raster layer", 
                    level=Qgis.Critical, duration=2)
            return


        i1, j1 = self.to_indexes(x1, y1)
        if self.snap_tolerance is not None:
            try:
                i1, j1 = self.snap(i1, j1)
            except OutsideMapError:
                return
            x1, y1 = self.to_coords(i1, j1)
        r, g, b, = self.sample
        try:
            r0 = r[i1, j1]
            g0 = g[i1, j1]
            b0 = b[i1, j1]
        except IndexError:
            self.iface.messageBar().pushMessage(
                "Outside Map",
                "Clicked outside of raster layer",
                level=Qgis.Warning, duration=1,
                )
            return

        self.anchor_points.append((x1, y1))
        self.anchor_points_ij.append((i1, j1))
        marker = QgsVertexMarker(self.canvas())
        marker.setCenter(QgsPointXY(x1, y1))
        self.markers.append(marker)

        # we need at least two points to draw
        if len(self.anchor_points) < 2:
            return

        if self.is_tracing:
            if self.grid_changed is None:
                grid = np.abs((r0 - r) ** 2 + (g0 - g) ** 2 + (b0 - b) ** 2)
            else:
                grid = self.grid_changed
            i0, j0 = self.anchor_points_ij[-2]
            start_point = i0, j0
            end_point = i1, j1


            # dirty hack to avoid QGIS crashing
            globals()['find_path_task'] = FindPathTask(
                grid.astype(np.dtype('l')),
                start_point,
                end_point,
                self.draw_path,
                vlayer,
                )
            QgsApplication.taskManager().addTask(find_path_task)
            self.tracking_is_active = True

        else:
            self.draw_path(
                None,
                vlayer,
                was_tracing=False,
                x1=x1,
                y1=y1,
                )

    def draw_path(self, path, vlayer, was_tracing=True,\
                  x1=None, y1=None):
        '''
        Draws a path after tracer found it.
        '''

        if was_tracing:
            if self.smooth_line:
                path = smooth(path, size=5)
                path = simplify(path)
            current_last_point = self.to_coords(*path[-1])
            path_ref = [self.to_coords_provider(i, j) for i, j in path]
        else:
            x0, y0 = self.anchor_points[-2]
            path_ref = [self.to_coords_provider2(x0, y0),
                        self.to_coords_provider2(x1, y1)]
            current_last_point = (x1, y1)

        if len(self.anchor_points) == 2:
            vlayer.beginEditCommand("Adding new line")
            add_feature_to_vlayer(vlayer, path_ref)
            vlayer.endEditCommand()
        else:
            last_point = self.to_coords_provider2(*self.anchor_points[-2])
            path_ref = [last_point] + path_ref[1:]
            vlayer.beginEditCommand("Adding new segment to the line")
            add_to_last_feature(vlayer, path_ref)
            vlayer.endEditCommand()
        self.anchor_points[-1] = current_last_point
        self.redraw()
        self.tracking_is_active = False


    def update_rubber_band(self):
        # this is very ugly but I can't make another way
        if self.last_mouse_event_pos is None:
            return

        if len(self.anchor_points) < 1:
            return
        x0, y0 = self.anchor_points[-1]
        qgsPoint = self.toMapCoordinates(self.last_mouse_event_pos)
        x1, y1 = qgsPoint.x(), qgsPoint.y()
        points = [QgsPoint(x0, y0), QgsPoint(x1, y1)]

        self.rubber_band.setColor(QColor(255, 0, 0))
        self.rubber_band.setWidth(3)
        if self.is_tracing:
            self.rubber_band.setLineStyle(Qt.DotLine)
        else:
            self.rubber_band.setLineStyle(Qt.SolidLine)
        vlayer = self.get_current_vector_layer()
        if vlayer is None:
            return
        self.rubber_band.setToGeometry(QgsGeometry.fromPolyline(points),
                                       self.vlayer)

    def canvasMoveEvent(self, mouseEvent):
        self.last_mouse_event_pos = mouseEvent.pos()

        if self.snap_tolerance is not None and self.is_tracing:
            qgsPoint = self.toMapCoordinates(mouseEvent.pos())
            x1, y1 = qgsPoint.x(), qgsPoint.y()
            # i, j = get_indxs_from_raster_coords(self.geo_ref, x1, y1)
            i, j = self.to_indexes(x1, y1)
            try:
                i1, j1 = self.snap(i, j)
            except OutsideMapError:
                return
            # x1, y1 = get_coords_from_raster_indxs(self.geo_ref, i1, j1)
            x1, y1 = self.to_coords(i1, j1)
            self.marker_snap.setCenter(QgsPointXY(x1, y1))

        # we need at least one point to draw
        if len(self.anchor_points) < 1:
            self.redraw()
            return

        self.update_rubber_band()
        self.redraw()

    def abort_tracing_process(self):

        # check if we have any tasks
        if globals()['find_path_task'] is None:
            return

        self.tracking_is_active = False

        try:
            # send terminate signal to the task
            globals()['find_path_task'].cancel()
        except RuntimeError:
            pass
            

    def redraw(self):
        # If caching is enabled, a simple canvas refresh might not be
        # sufficient to trigger a redraw and you must clear the cached image
        # for the layer
        if self.iface.mapCanvas().isCachingEnabled():
            vlayer = self.get_current_vector_layer()
            if vlayer is None:
                return
            vlayer.triggerRepaint()
        else:
            self.iface.mapCanvas().refresh()


def add_to_last_feature(vlayer, points):
    features = [f for f in vlayer.getFeatures()]
    last_feature = features[-1]
    fid = last_feature.id()
    geom = last_feature.geometry()
    points = [QgsPointXY(x, y) for x, y in points]
    geom.addPointsXY(points)
    vlayer.changeGeometry(fid, geom)


def add_feature_to_vlayer(vlayer, points):
    feat = QgsFeature(vlayer.fields())
    polyline = [QgsPoint(x, y) for x, y in points]
    feat.setGeometry(QgsGeometry.fromPolyline(polyline))
    vlayer.addFeature(feat)

