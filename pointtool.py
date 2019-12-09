from qgis.core import QgsPointXY, QgsPoint, QgsGeometry, QgsFeature
from qgis.gui import QgsMapToolEmitPoint, QgsMapToolEdit, \
                     QgsRubberBand, QgsVertexMarker
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import Qgis

import numpy as np
#import matplotlib.pyplot as plt


from .astar import find_path
from .line_simplification import smooth, simplify
from .utils import get_indxs_from_raster_coords, get_coords_from_raster_indxs, get_whole_raster


class OutsideMapError(Exception):
    pass

class PointTool(QgsMapToolEdit):

    def __init__(self, canvas, iface, turn_off_snap):
        self.last_mouse_event_pos = None
        self.iface = iface
        self.anchor_points = []
        self.anchor_points_ij = []
        self.is_tracing = True
        self.turn_off_snap = turn_off_snap

        # possible variants: gray_diff, as_is, color_diff (using v from hsv)
        self.grid_conversion = "gray_diff"

        #QApplication.restoreOverrideCursor()
        #QApplication.setOverrideCursor(Qt.CrossCursor)
        QgsMapToolEmitPoint.__init__(self, canvas)

        self.rlayer = None
        self.grid_changed = None
        self.snap_tolerance = None
        self.vlayer = None

        self.rubber_band = QgsRubberBand(self.canvas(), False)  # False = not a polygon
        self.markers = []
        self.marker_snap = QgsVertexMarker(self.canvas())
        self.marker_snap.setColor(QColor(255, 0, 255))

    def snap_tolerance_changed(self, snap_tolerance):
        self.snap_tolerance = snap_tolerance
        if snap_tolerance is None:
            self.marker_snap.hide()
        else:
            self.marker_snap.show()

    def trace_color_changed(self, color):
        r,g,b = self.sample 

        if color is False:
            self.grid_changed = None
        else:
            r0,g0,b0,t = color.getRgb()
            self.grid_changed = np.abs( (r0-r)**2 + (g0-g)**2 + (b0-b)**2 )

    def get_current_vector_layer(self):
        try:
            vlayer = self.iface.layerTreeView().selectedLayers()[0]
            return vlayer
        except IndexError:
            self.iface.messageBar().pushMessage("Missing Layer", 
                    "Please select vector layer to draw", 
                    level=Qgis.Warning)
            return None

    def raster_layer_has_changed(self, raster_layer):
        self.rlayer = raster_layer
        if self.rlayer is None:
            self.iface.messageBar().pushMessage("Missing Layer", 
                    "Please select raster layer to trace", 
                    level=Qgis.Warning)
            return

        sample, geo_ref = get_whole_raster(self.rlayer)

        r = sample[0].astype(float)
        g = sample[1].astype(float)
        b = sample[2].astype(float)
        where_are_NaNs = np.isnan(r)
        r[where_are_NaNs] = 0
        where_are_NaNs = np.isnan(g)
        g[where_are_NaNs] = 0
        where_are_NaNs = np.isnan(b)
        b[where_are_NaNs] = 0
        
        self.sample = (r,g,b)
        self.grid = r+g+b
        self.geo_ref = geo_ref

    def keyPressEvent(self, e):
        # delete last segment if backspace is pressed
        if e.key() == Qt.Key_Backspace or e.key() == Qt.Key_B:
            # check if we have at least one feature to delete
            vlayer = self.get_current_vector_layer()
            if vlayer is None: return
            if vlayer.featureCount() < 1: return 

            remove_last_feature(vlayer)

            # remove last marker
            if len(self.markers)>0: 
                last_marker = self.markers.pop()
                self.canvas().scene().removeItem(last_marker)

            # remove last anchor
            if len(self.anchor_points)>0: 
                self.anchor_points.pop()
                self.anchor_points_ij.pop()

            self.update_rubber_band()
            self.redraw()

        elif e.key() == Qt.Key_A:
            self.is_tracing = not self.is_tracing
            self.update_rubber_band()
        elif e.key() == Qt.Key_S:
            self.turn_off_snap()



    def snap(self, i, j):
        if self.snap_tolerance is None: return i,j
        if not self.is_tracing: return i,j
        if self.grid_changed is None: return i,j

        size_i, size_j = self.grid.shape
        size = self.snap_tolerance

        if i<size or j<size or i+size>size_i or j+size>size_j:
            raise OutsideMapError

        grid_small = self.grid_changed
        grid_small = grid_small[ i-size : i+size, j-size : j+size ] 

        smallest_cells = np.where(grid_small == np.amin(grid_small))
        coordinates = list(zip(smallest_cells[0], smallest_cells[1]))

        if len(coordinates) == 1:
            delta_i, delta_j = coordinates[0]
            delta_i -= size
            delta_j -= size
        else:
            # find the closest to the center
            deltas = [(i-size, j-size) for i,j in coordinates]
            lengths = [(i**2 + j**2) for i,j in deltas]
            i = lengths.index(min(lengths))
            delta_i, delta_j = deltas[i]

        return i+delta_i, j+delta_j


    def canvasReleaseEvent(self, mouseEvent):
        vlayer = self.get_current_vector_layer()
        if vlayer is None: return

        if self.rlayer is None:
            self.iface.messageBar().pushMessage("Missing Layer", 
                    "Please select raster layer to trace", 
                    level=Qgis.Warning)
        self.last_mouse_event_pos = mouseEvent.pos()
        # hide rubber_band
        self.rubber_band.hide()

        if (mouseEvent.button()==Qt.RightButton):
            # finish point path if it was last point
            self.anchor_points = []

            # hide all markers
            while len(self.markers)>0:
                marker = self.markers.pop()
                self.canvas().scene().removeItem(marker)
            return

        qgsPoint = self.toMapCoordinates(mouseEvent.pos())
        x1, y1 = qgsPoint.x(), qgsPoint.y()
        i, j = get_indxs_from_raster_coords(self.geo_ref, x1, y1)
        try:
            i1, j1 = self.snap(i, j)
        except OutsideMapError:
            return
        x1, y1 = get_coords_from_raster_indxs(self.geo_ref, i1, j1) 
        self.anchor_points.append((x1,y1))
        self.anchor_points_ij.append((i1,j1))
        marker = QgsVertexMarker(self.canvas())
        marker.setCenter(QgsPointXY(x1,y1))
        self.markers.append(marker)

        # we need at least two points to draw
        if len(self.anchor_points)<2: return 

        if self.is_tracing:
            if self.grid_changed is None:
                r, g, b, = self.sample
                r0 = r[i1,j1]
                g0 = g[i1,j1]
                b0 = b[i1,j1]
                grid = np.abs( (r0-r)**2 + (g0-g)**2 + (b0-b)**2 )
            else:
                grid = self.grid_changed
            i0, j0 = self.anchor_points_ij[-2]
            start_point = i0, j0
            end_point = i1, j1

            path = find_path(grid.astype(np.dtype('l')), start_point, end_point)
            path = smooth(path, size=5)
            path = simplify(path)
            path_ref = [get_coords_from_raster_indxs(self.geo_ref, i, j) 
                                                                for i,j in path]
        else:
            x0, y0 = self.anchor_points[-2]
            path_ref = [(x0,y0),  (x1,y1)]

        add_features_to_vlayer(vlayer, path_ref)
        self.redraw()


    def update_rubber_band(self):
        # this is very ugly but I can't make another way
        if self.last_mouse_event_pos is None: return

        if len(self.anchor_points)<1: return
        x0, y0 = self.anchor_points[-1]
        qgsPoint = self.toMapCoordinates(self.last_mouse_event_pos)
        x1, y1 = qgsPoint.x(), qgsPoint.y()
        points = [QgsPoint(x0, y0), QgsPoint(x1,y1)]

        self.rubber_band.setColor(QColor(255, 0, 0))
        self.rubber_band.setWidth(3)
        if self.is_tracing:
            self.rubber_band.setLineStyle(Qt.DotLine)
        else:
            self.rubber_band.setLineStyle(Qt.SolidLine)
        vlayer = self.get_current_vector_layer()
        if vlayer is None: return
        self.rubber_band.setToGeometry(QgsGeometry.fromPolyline(points), self.vlayer)



    def canvasMoveEvent(self, mouseEvent): 
        self.last_mouse_event_pos = mouseEvent.pos()

        if self.snap_tolerance is not None and self.is_tracing:
            qgsPoint = self.toMapCoordinates(mouseEvent.pos())
            x1, y1 = qgsPoint.x(), qgsPoint.y()
            i, j = get_indxs_from_raster_coords(self.geo_ref, x1, y1)
            try:
                i1, j1 = self.snap(i, j)
            except OutsideMapError:
                return
            x1, y1 = get_coords_from_raster_indxs(self.geo_ref, i1, j1) 
            self.marker_snap.setCenter(QgsPointXY(x1,y1))

        # we need at least one point to draw
        if len(self.anchor_points) < 1: 
            self.redraw()
            return 

        self.update_rubber_band()
        self.redraw()

    def redraw(self):
        # If caching is enabled, a simple canvas refresh might not be sufficient
        # to trigger a redraw and you must clear the cached image for the layer
        if self.iface.mapCanvas().isCachingEnabled():
            vlayer = self.get_current_vector_layer()
            if vlayer is None: return
            vlayer.triggerRepaint()
        else:
            self.iface.mapCanvas().refresh()




def remove_last_feature(vlayer):
    features = [f for f in vlayer.getFeatures()]
    vlayer.deleteFeatures([features[-1].id()])


def add_features_to_vlayer(vlayer, points):
    feat = QgsFeature(vlayer.fields())
    polyline = [QgsPoint(x,y) for x,y in points]
    feat.setGeometry(QgsGeometry.fromPolyline(polyline))
    (res, outFeats) = vlayer.dataProvider().addFeatures([feat])

