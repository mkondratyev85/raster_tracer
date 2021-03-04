'''
Module contains States for pointtool.
'''

from math import atan2, cos, sin, radians

from qgis.core import QgsApplication

from .autotrace import AutotraceSubTask


class State:
    '''
    Abstract class for the state
    '''

    def __init__(self, pointtool):
        self.pointtool = pointtool

    def click_rmb(self, mouseEvent, vlayer):
        '''
        Event when the user clicks on the map with the right button
        '''

        # finish point path if it was last point
        self.pointtool.anchors = []

        # hide all markers
        while self.pointtool.markers:
            marker = self.pointtool.markers.pop()
            self.pointtool.canvas().scene().removeItem(marker)

        # hide rubber_band
        self.pointtool.rubber_band.hide()

        # change state
        self.pointtool.change_state(WaitingFirstPointState)

    def click_lmb(self, mouseEvent, vlayer):
        '''
        Event when the user clicks on the map with the left button
        '''

        # self.pointtool.last_mouse_event_pos = mouseEvent.pos()
        # hide rubber_band
        self.pointtool.rubber_band.hide()

        # check if he haven't any new tasks yet
        if self.pointtool.tracking_is_active:
            self.pointtool.display_message(
                " ",
                "Please wait till the last segment is finished" +
                " or terminate tracing by hitting Esc",
                level='Critical',
                duration=1,
                )
            return False

        # acquire point coordinates from mouseEvent
        qgsPoint = self.pointtool.toMapCoordinates(mouseEvent.pos())
        x1, y1 = qgsPoint.x(), qgsPoint.y()

        if self.pointtool.to_indexes is None:
            self.pointtool.display_message(
                "Missing Layer",
                "Please select correct raster layer",
                level='Critical',
                duration=2,
                )
            return False

        if self.pointtool.snap2_tolerance:
            x1, y1 = self.pointtool.snap_to_itself(x1, y1, self.pointtool.snap2_tolerance)
        i1, j1 = self.pointtool.to_indexes(x1, y1)
        self.pointtool.add_anchor_points(x1, y1, i1, j1)

        return True


class WaitingFirstPointState(State):
    '''
    State of waiting the user to click on the first point in the line.
    Is active when the user is about to begin tracing new line.
    After the user clicks on the left mouse button
    it changes the state to WaitingMiddlePointState.
    '''

    def click_lmb(self, mouseEvent, vlayer):

        if super().click_lmb(mouseEvent, vlayer) is False:
            return

        # change state
        self.pointtool.change_state(WaitingMiddlePointState)
        # self.pointtool.change_state(AutoFollowingLineState)

    def click_rmb(self, mouseEvent, vlayer):
        pass


class WaitingMiddlePointState(State):
    '''
    State of waiting the user to click on the next point in the line.
    Is active when the user is already clicked on at least one point.
    After the user clicks on the left mouse button it keeps the state.
    After the user clicks on the right mouse button it finishes the line and
    switches the state to WaitingFirstPointState.

    '''

    def click_lmb(self, mouseEvent, vlayer):
        if super().click_lmb(mouseEvent, vlayer) is False:
            return

        x1, y1, i1, j1 = self.pointtool.anchors[-1]

        if self.pointtool.tracing_mode.is_auto():

            # perform autotrace
            self.autotrace_task = AutotraceSubTask(
                self.pointtool,
                vlayer,
                clicked_point=self.pointtool.anchors[-1],
                )
            # self.pointtool.remove_last_anchor_point(undo_edit=False, redraw=False)

            QgsApplication.taskManager().addTask(
                self.autotrace_task,
                )

        else:
            self.pointtool.trace(x1, y1, i1, j1, vlayer)

    def click_rmb(self, mouseEvent, vlayer):

        super().click_rmb(mouseEvent, vlayer)

        # # add last feature to spatial index to perform fast search of closet points
        # self.pointtool.add_last_feature_to_spindex(vlayer)


class AutoFollowingLineState(State):
    '''
    This state is active when raster_tracer is trying to
    perform auto-following of the line.
    '''

    def click_lmb(self, mouseEvent, vlayer):
        if super().click_lmb(mouseEvent, vlayer) is False:
            return

        self.follow_next_segment(vlayer, initial=True)

        for _ in range(25):
            self.follow_next_segment(vlayer)
            # while True:
            #     if self.pointtool.ready is True:
            #         break
            self.pointtool.redraw()
            self.pointtool.update_rubber_band()
            # print('a')
         

    def click_rmb(self, mouseEvent, vlayer):
        super().click_rmb(mouseEvent, vlayer)

    def follow_next_segment(self, vlayer, initial=False):
        _, _, i0, j0 = self.pointtool.anchors[-2]
        _, _, i1, j1 = self.pointtool.anchors[-1]

        direction = atan2(j1 - j0, i1 - i0)
        distance = 5

        if initial:
            self.pointtool.remove_last_anchor_point(undo_edit=False)
            i1, j1 = i0, j0

        points = self.search_near_points((i1, j1), direction, distance)

        costs = []
        paths = []

        for point in points:
            i2, j2 = point
            x2, y2 = self.pointtool.to_coords(i2, j2)

            path, cost = self.pointtool.trace_over_image((i1, j1), (i2, j2))
            costs.append(cost)
            paths.append(path)

        min_cost = min(costs)
        min_cost_index = costs.index(min_cost)

        best_point = points[min_cost_index]
        best_path = paths[min_cost_index]
        i, j = best_point
        x, y = self.pointtool.to_coords(i, j)

        if len(self.pointtool.anchors)>1:
            self.pointtool.draw_path(best_path, vlayer, was_tracing=True)
            self.pointtool.add_anchor_points(x, y, i, j)
        else:
            self.pointtool.add_anchor_points(x, y, i, j)
            self.pointtool.draw_path(best_path, vlayer, was_tracing=True)

        self.pointtool.pan(x, y)

    def search_near_points(self, point, direction, distance):
        '''
        Returns list of points near last point in the given direction,
        at a given distance with given space between points.
        '''

        points = []

        i1, j1 = point

        angles = [direction + radians(i) for i in range(-60, 60, 10)]

        for angle in angles:
            i2 = i1 + distance * cos(angle)
            j2 = j1 + distance * sin(angle)

            points.append((int(i2), int(j2)))

        return points
