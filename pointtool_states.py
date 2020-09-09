'''
Module contains States for pointtool.
'''

from math import atan2, cos, sin, radians


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

    def click_lmb(self, mouseEvent, vlayer):
        '''
        Event when the user clicks on the map with the left button
        '''

        self.pointtool.last_mouse_event_pos = mouseEvent.pos()
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

        i1, j1 = self.pointtool.to_indexes(x1, y1)

        self.pointtool.add_anchor_points(x1, y1, i1, j1)

        self.current_point = x1, y1, i1, j1

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


class WaitingMiddlePointState(State):
    '''
    State of waithing the user to click on the next point in the line.
    Is active when the user is already clicked on at least one point.
    After the user clicks on the left mouse button it keeps the state.
    After the user clicks on the right mouse button it finishes the line and
    switches the state to WaitingFirstPointState.

    '''

    def click_lmb(self, mouseEvent, vlayer):
        if super().click_lmb(mouseEvent, vlayer) is False:
            return

        x1, y1, i1, j1 = self.current_point

        self.pointtool.trace(x1, y1, i1, j1, vlayer)

        if True:
            self.pointtool.change_state(AutoFollowingLineState)

            for _ in range(25):
                self.pointtool.state.begin_autofollowing(vlayer)

            self.pointtool.change_state(WaitingMiddlePointState)

    def click_rmb(self, mouseEvent, vlayer):

        # finish point path if it was last point
        self.pointtool.anchor_points = []

        # hide all markers
        while self.pointtool.markers:
            marker = self.pointtool.markers.pop()
            self.pointtool.canvas().scene().removeItem(marker)

        # hide rubber_band
        self.pointtool.rubber_band.hide()

        # change state
        self.pointtool.change_state(WaitingFirstPointState)


class AutoFollowingLineState(State):
    '''
    This state is active when raster_tracer is trying to
    perform auto-following of the line.
    '''

    def begin_autofollowing(self, vlayer):
        # x1, y1 = self.pointtool.anchor_points[-1]
        i1, j1 = self.pointtool.anchor_points_ij[-1]
        # x0, y0 = self.pointtool.anchor_points[-2]
        i0, j0 = self.pointtool.anchor_points_ij[-2]
        direction = atan2(j1 - j0, i1 - i0)
        distance = 5
        points = self.search_near_points((i1, j1), direction, distance)

        costs = []
        paths = []

        for point in points:
            i2, j2 = point
            x2, y2 = self.pointtool.to_coords(i2, j2)

            # self.pointtool.add_anchor_points(x2, y2, i2, j2)

            path, cost = self.pointtool.trace_over_image((i1, j1), (i2, j2))
            costs.append(cost)
            paths.append(path)

        min_cost = min(costs)
        min_cost_index = costs.index(min_cost)

        best_point = points[min_cost_index]
        best_path = paths[min_cost_index]
        i, j = best_point
        x, y = self.pointtool.to_coords(i, j)

        self.pointtool.add_anchor_points(x, y, i, j)
        self.pointtool.draw_path(best_path, vlayer)

        # self.pointtool.trace(x, y, i, j, vlayer)

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
