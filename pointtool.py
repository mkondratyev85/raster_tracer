'''
Main functionality of raster tracer.
'''

from enum import Enum
from collections import namedtuple
import numpy as np

from qgis.core import QgsPointXY, QgsPoint, QgsGeometry, QgsFeature, \
                      QgsVectorLayer, QgsProject, QgsWkbTypes, QgsApplication, \
                      QgsRectangle, QgsSpatialIndex
from qgis.gui import QgsMapToolEmitPoint, QgsMapToolEdit, \
                     QgsRubberBand, QgsVertexMarker, QgsMapTool
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import Qgis
from qgis.core import QgsCoordinateTransform


from .astar import FindPathTask, FindPathFunction
from .line_simplification import smooth, simplify
from .utils import get_whole_raster, PossiblyIndexedImageError
from .pointtool_states import WaitingFirstPointState
from .exceptions import OutsideMapError

# An point on the map where the user clicked along the line
Anchor = namedtuple('Anchor', ['x', 'y', 'i', 'j'])

# Flag for experimental Autofollowing mode
ALLOW_AUTO_FOLLOWING = False


class TracingModes(Enum):
    '''
    Possible Tracing Modes for Pointtool.
    LINE - straight line from start to end.
    PATH - tracing along color from start to end.
    AUTO - auto tracing mode along color in the given direction.
    '''

    LINE = 1
    PATH = 2
    AUTO = 3

    def next(self):
        '''
        Switches between LINE and PATH
        '''
        cls = self.__class__
        members = list(cls)

        if not ALLOW_AUTO_FOLLOWING:
            return members[0] if self.value == 2 else members[1]

        index = members.index(self) + 1
        if index >= len(members):
            index = 0
        return members[index]

    def is_tracing(self):
        '''
        Returns True if mode is PATH
        '''
        return True if self.value == 2 else False

    def is_auto(self):
        '''
        Returns True if mode is PATH
        '''
        return True if self.value == 3 else False


# Line styles for the rubber band
RUBBERBAND_LINE_STYLES = {
    TracingModes.PATH: Qt.DotLine,
    TracingModes.LINE: Qt.SolidLine,
    TracingModes.AUTO: Qt.DashDotLine,
    }


class PointTool(QgsMapToolEdit):
    '''
    Implementation of interactions of the user with the main map.
    Will called every time the user clicks on the map
    or hovers the mouse over the map.
    '''

    def deactivate(self):
        QgsMapTool.deactivate(self)
        self.deactivated.emit()

    def __init__(self, canvas, iface, turn_off_snap, smooth=False):
        '''
        canvas - link to the QgsCanvas of the application
        iface - link to the Qgis Interface
        turn_off_snap - flag sets snapping to the nearest color
        smooth - flag sets smoothing of the traced path
        '''

        self.iface = iface

        # list of Anchors for current line
        self.anchors = []

        # for keeping track of mouse event for rubber band updating
        self.last_mouse_event_pos = None

        self.tracing_mode = TracingModes.PATH

        self.turn_off_snap = turn_off_snap
        self.smooth_line = smooth

        # possible variants: gray_diff, as_is, color_diff (using v from hsv)
        self.grid_conversion = "gray_diff"

        # QApplication.restoreOverrideCursor()
        # QApplication.setOverrideCursor(Qt.CrossCursor)
        QgsMapToolEmitPoint.__init__(self, canvas)

        self.rlayer = None
        self.grid_changed = None
        self.snap_tolerance = None # snap to color
        self.snap2_tolerance = None # snap to itself
        self.vlayer = None
        self.grid = None
        self.sample = None

        self.tracking_is_active = False

        # False = not a polygon
        self.rubber_band = QgsRubberBand(self.canvas(), QgsWkbTypes.LineGeometry)
        self.markers = []
        self.marker_snap = QgsVertexMarker(self.canvas())
        self.marker_snap.setColor(QColor(255, 0, 255))

        self.find_path_task = None

        self.change_state(WaitingFirstPointState)

        self.last_vlayer = None

    def display_message(self,
                        title,
                        message,
                        level='Info',
                        duration=2,
                        ):
        '''
        Shows message bar to the user.
        `level` receives one of four possible string values:
            Info, Warning, Critical, Success
        '''

        LEVELS = {
            'Info': Qgis.Info,
            'Warning': Qgis.Warning,
            'Critical': Qgis.Critical,
            'Success': Qgis.Success,
        }

        self.iface.messageBar().pushMessage(
            title,
            message,
            LEVELS[level],
            duration)

    def change_state(self, state):
        self.state = state(self)

    def snap_tolerance_changed(self, snap_tolerance):
        self.snap_tolerance = snap_tolerance
        if snap_tolerance is None:
            self.marker_snap.hide()
        else:
            self.marker_snap.show()

    def snap2_tolerance_changed(self, snap_tolerance):
        self.snap2_tolerance = snap_tolerance**2
        # if snap_tolerance is None:
        #     self.marker_snap.hide()
        # else:
        #     self.marker_snap.show()

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
                if vlayer.wkbType() == QgsWkbTypes.MultiLineString:
                    # if self.last_vlayer:
                    #     if vlayer != self.last_vlayer:
                    #         self.create_spatial_index_for_vlayer(vlayer)
                    # else:
                    #     self.create_spatial_index_for_vlayer(vlayer)
                    # self.last_vlayer = vlayer
                    return vlayer
                else:
                    self.display_message(
                        " ",
                        "The active layer must be" +
                        " a MultiLineString vector layer",
                        level='Warning',
                        duration=2,
                        )
                    return None
            else:
                self.display_message(
                    "Missing Layer",
                    "Please select vector layer to draw",
                    level='Warning',
                    duration=2,
                    )
                return None
        except IndexError:
            self.display_message(
                "Missing Layer",
                "Please select vector layer to draw",
                level='Warning',
                duration=2,
                )
            return None

    def raster_layer_has_changed(self, raster_layer):
        self.rlayer = raster_layer
        if self.rlayer is None:
            self.display_message(
                "Missing Layer",
                "Please select raster layer to trace",
                level='Warning',
                duration=2,
                )
            return

        try:
            sample, to_indexes, to_coords, to_coords_provider, \
                to_coords_provider2 = \
                get_whole_raster(self.rlayer,
                                 QgsProject.instance(),
                                 )
        except PossiblyIndexedImageError:
            self.display_message(
                "Missing Layer",
                "Can't trace indexed or gray image",
                level='Critical',
                duration=2,
                )
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

    def remove_last_anchor_point(self, undo_edit=True, redraw=True):
        '''
        Removes last anchor point and last marker point
        '''

        # check if we have at least one feature to delete
        vlayer = self.get_current_vector_layer()
        if vlayer is None:
            return
        if vlayer.featureCount() < 1:
            return

        # remove last marker
        if self.markers:
            last_marker = self.markers.pop()
            self.canvas().scene().removeItem(last_marker)

        # remove last anchor
        if self.anchors:
            self.anchors.pop()

        if undo_edit:
            # it's a very ugly way of triggering single undo event
            self.iface.editMenu().actions()[0].trigger()

        if redraw:
            self.update_rubber_band()
            self.redraw()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Backspace or e.key() == Qt.Key_B:
            # delete last segment if backspace is pressed
            self.remove_last_anchor_point()
        elif e.key() == Qt.Key_A:
            # change tracing mode
            self.tracing_mode = self.tracing_mode.next()
            self.update_rubber_band()
        elif e.key() == Qt.Key_S:
            # toggle snap mode
            self.turn_off_snap()
        elif e.key() == Qt.Key_Escape:
            # Abort tracing process
            self.abort_tracing_process()

    def add_anchor_points(self, x1, y1, i1, j1):
        '''
        Adds anchor points and markers to self.
        '''

        anchor = Anchor(x1, y1, i1, j1)
        self.anchors.append(anchor)

        marker = QgsVertexMarker(self.canvas())
        marker.setCenter(QgsPointXY(x1, y1))
        self.markers.append(marker)

    def trace_over_image(self,
                         start,
                         goal,
                         do_it_as_task=False,
                         vlayer=None):
        '''
        performs tracing
        '''

        i0, j0 = start
        i1, j1 = goal

        r, g, b, = self.sample

        try:
            r0 = r[i1, j1]
            g0 = g[i1, j1]
            b0 = b[i1, j1]
        except IndexError:
            raise OutsideMapError

        if self.grid_changed is None:
            grid = np.abs((r0 - r) ** 2 + (g0 - g) ** 2 + (b0 - b) ** 2)
        else:
            grid = self.grid_changed

        if do_it_as_task:
            # dirty hack to avoid QGIS crashing
            self.find_path_task = FindPathTask(
                grid.astype(np.dtype('l')),
                start,
                goal,
                self.draw_path,
                vlayer,
                )

            QgsApplication.taskManager().addTask(
                self.find_path_task,
                )
            self.tracking_is_active = True
        else:
            path, cost = FindPathFunction(
                grid.astype(np.dtype('l')),
                (i0, j0),
                (i1, j1),
                )
            return path, cost

    def trace(self, x1, y1, i1, j1, vlayer):
        '''
        Traces path from last point to given point.
        In case tracing is inactive just creates
        straight line.
        '''

        if self.tracing_mode.is_tracing():
            if self.snap_tolerance is not None:
                try:
                    i1, j1 = self.snap(i1, j1)
                except OutsideMapError:
                    return

            _, _, i0, j0 = self.anchors[-2]
            start_point = i0, j0
            end_point = i1, j1
            try:
                self.trace_over_image(start_point,
                                      end_point,
                                      do_it_as_task=True,
                                      vlayer=vlayer)
            except OutsideMapError:
                pass
        else:
            self.draw_path(
                None,
                vlayer,
                was_tracing=False,
                x1=x1,
                y1=y1,
                )

    def snap_to_itself(self, x, y, sq_tolerance=1):
        '''
        finds a nearest segment line to the current vlayer
        '''

        pt = QgsPointXY(x, y)
        # nearest_feature_id = self.spIndex.nearestNeighbor(pt, 1, tolerance)[0]
        vlayer = self.get_current_vector_layer()
        # feature = vlayer.getFeature(nearest_feature_id)
        for feature in vlayer.getFeatures():
            closest_point, _, _, _, sq_distance = feature.geometry().closestVertex(pt)
            if sq_distance < sq_tolerance:
                return closest_point.x(), closest_point.y()
        return x, y

    def snap(self, i, j):
        if self.snap_tolerance is None:
            return i, j
        if not self.tracing_mode.is_tracing():
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
        '''
        Method where the actual tracing is performed
        after the user clicked on the map
        '''

        vlayer = self.get_current_vector_layer()

        if vlayer is None:
            return

        if not vlayer.isEditable():
            self.display_message(
                "Edit mode",
                "Please begin editing vector layer to trace",
                level='Warning',
                duration=2,
                )
            return

        if self.rlayer is None:
            self.display_message(
                "Missing Layer",
                "Please select raster layer to trace",
                level='Warning',
                duration=2,
                )
            return

        if mouseEvent.button() == Qt.RightButton:
            self.state.click_rmb(mouseEvent, vlayer)
        elif mouseEvent.button() == Qt.LeftButton:
            self.state.click_lmb(mouseEvent, vlayer)

        return

    def draw_path(self, path, vlayer, was_tracing=True,\
                  x1=None, y1=None):
        '''
        Draws a path after tracer found it.
        '''

        transform = QgsCoordinateTransform(QgsProject.instance().crs(),
                                           vlayer.crs(),
                                           QgsProject.instance())
        if was_tracing:
            if self.smooth_line:
                path = smooth(path, size=5)
                path = simplify(path)
            vlayer = self.get_current_vector_layer()
            current_last_point = self.to_coords(*path[-1])
            path_ref = [transform.transform(*self.to_coords_provider(i, j)) for i, j in path]
            x0, y0, _, _ = self.anchors[-2]
            last_point = transform.transform(*self.to_coords_provider2(x0, y0))
            path_ref = [last_point] + path_ref[1:]
        else:
            x0, y0, _i, _j = self.anchors[-2]
            current_last_point = (x1, y1)
            path_ref = [transform.transform(*self.to_coords_provider2(x0, y0)),
                        transform.transform(*self.to_coords_provider2(x1, y1))]


        self.ready = False
        if len(self.anchors) == 2:
            vlayer.beginEditCommand("Adding new line")
            add_feature_to_vlayer(vlayer, path_ref)
            vlayer.endEditCommand()
        else:
            vlayer.beginEditCommand("Adding new segment to the line")
            add_to_last_feature(vlayer, path_ref)
            vlayer.endEditCommand()
        _, _, current_last_point_i, current_last_point_j = self.anchors[-1]
        self.anchors[-1] = current_last_point[0], current_last_point[1], current_last_point_i, current_last_point_j
        self.redraw()
        self.tracking_is_active = False


    def update_rubber_band(self):
        # this is very ugly but I can't make another way
        if self.last_mouse_event_pos is None:
            return

        if not self.anchors:
            return

        x0, y0, _, _ = self.anchors[-1]
        qgsPoint = self.toMapCoordinates(self.last_mouse_event_pos)
        x1, y1 = qgsPoint.x(), qgsPoint.y()
        points = [QgsPoint(x0, y0), QgsPoint(x1, y1)]

        self.rubber_band.setColor(QColor(255, 0, 0))
        self.rubber_band.setWidth(3)

        self.rubber_band.setLineStyle(
            RUBBERBAND_LINE_STYLES[self.tracing_mode],
            )

        vlayer = self.get_current_vector_layer()
        if vlayer is None:
            return

        self.rubber_band.setToGeometry(
            QgsGeometry.fromPolyline(points),
            self.vlayer,
            )

    def canvasMoveEvent(self, mouseEvent):
        '''
        Store the mouse position for the correct
        updating of the rubber band
        '''

        # we need at least one point to draw
        if not self.anchors:
            return

        if self.snap_tolerance is not None and self.tracing_mode.is_tracing():
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

        self.last_mouse_event_pos = mouseEvent.pos()
        self.update_rubber_band()
        self.redraw()

    def abort_tracing_process(self):
        '''
        Terminate background process of tracing raster
        after the user hits Esc.
        '''

        # check if we have any tasks
        if self.find_path_task is None:
            return

        self.tracking_is_active = False

        try:
            # send terminate signal to the task
            self.find_path_task.cancel()
            self.find_path_task = None
        except RuntimeError:
            return
        else:
            self.remove_last_anchor_point(
                    undo_edit=False,
                    )

    def redraw(self):
        # If caching is enabled, a simple canvas refresh might not be
        # sufficient to trigger a redraw and you must clear the cached image
        # for the layer
        if self.iface.mapCanvas().isCachingEnabled():
            vlayer = self.get_current_vector_layer()
            if vlayer is None:
                return
            vlayer.triggerRepaint()

        self.iface.mapCanvas().refresh()
        QgsApplication.processEvents()

    def pan(self, x, y):
        '''
        Move the canvas to the x, y position
        '''
        currExt = self.iface.mapCanvas().extent()
        canvasCenter = currExt.center()
        dx = x - canvasCenter.x()
        dy = y - canvasCenter.y()
        xMin = currExt.xMinimum() + dx
        xMax = currExt.xMaximum() + dx
        yMin = currExt.yMinimum() + dy
        yMax = currExt.yMaximum() + dy
        newRect = QgsRectangle(xMin, yMin, xMax, yMax)
        self.iface.mapCanvas().setExtent(newRect)

    def add_last_feature_to_spindex(self, vlayer):
        '''
        Adds last feature to spatial index
        '''
        features = list(vlayer.getFeatures())
        last_feature = features[-1]
        self.spIndex.insertFeature(last_feature)

    def create_spatial_index_for_vlayer(self, vlayer):
        '''
        Creates spatial index for the vlayer
        '''

        self.spIndex = QgsSpatialIndex()
        # features = [f for f in vlayer]
        self.spIndex.addFeatures(vlayer.getFeatures())



def add_to_last_feature(vlayer, points):
    '''
    Adds points to the last line feature in the vlayer
    vlayer - QgsLayer of type MultiLine string
    points - list of points
    '''
    features = list(vlayer.getFeatures())
    last_feature = features[-1]
    fid = last_feature.id()
    geom = last_feature.geometry()
    points = [QgsPointXY(x, y) for x, y in points]
    geom.addPointsXY(points)
    vlayer.changeGeometry(fid, geom)


def add_feature_to_vlayer(vlayer, points):
    '''
    Adds new line feature to the vlayer
    '''

    feat = QgsFeature(vlayer.fields())
    polyline = [QgsPoint(x, y) for x, y in points]
    feat.setGeometry(QgsGeometry.fromPolyline(polyline))
    vlayer.addFeature(feat)

