'''
Module contains States for pointtool.
'''

from qgis.core import Qgis

from .exceptions import OutsideMapError


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
            self.pointtool.iface.messageBar().pushMessage(
                " ",
                "Please wait till the last segment is finished or terminate tracing by hitting Esc",
                level=Qgis.Critical,
                duration=1,
                )
            return False

        # acquire point coordinates from mouseEvent
        qgsPoint = self.pointtool.toMapCoordinates(mouseEvent.pos())
        x1, y1 = qgsPoint.x(), qgsPoint.y()

        if self.pointtool.to_indexes is None:
            self.pointtool.iface.messageBar().pushMessage(
                "Missing Layer",
                "Please select correct raster layer",
                level=Qgis.Critical,
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

