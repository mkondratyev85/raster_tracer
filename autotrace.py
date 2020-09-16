from math import atan2, cos, sin, radians

from qgis.core import QgsTask, QgsMessageLog


class AutotraceSubTask(QgsTask):

    def __init__(self, pointtool, vlayer, clicked_point=None):
        super().__init__(
            'Task for switching mode to autotrace',
            QgsTask.CanCancel
                )
        self.pointtool = pointtool
        self.vlayer = vlayer
        self.pseudo_anchors = []
        self.path = []
        self.clicked_point = clicked_point

    def run(self):

        if self.clicked_point:
            self.pseudo_anchors.append(self.pointtool.anchors[-1])
            self.pseudo_anchors.append(self.clicked_point)
            self.clicked_point = None
        else:
            self.pseudo_anchors.append(self.pointtool.anchors[-2])
            self.pseudo_anchors.append(self.pointtool.anchors[-1])

        result_path = self.follow_next_segment(initial=True)
        self.path += result_path


        for _ in range(5):
            # check isCanceled() to handle cancellation
            if self.isCanceled():
                return False

            result_path = self.follow_next_segment()
            self.path += result_path[1:]

        return True


    def follow_next_segment(self, initial=False):
        _, _, i0, j0 = self.pseudo_anchors[-2]
        _, _, i1, j1 = self.pseudo_anchors[-1]

        direction = atan2(j1 - j0, i1 - i0)
        distance = 5

        if initial:
            # self.pointtool.remove_last_anchor_point(undo_edit=False, redraw=False)
            self.pseudo_anchors.pop()
            i1, j1 = i0, j0

        points = self.search_near_points((i1, j1), direction, distance)

        costs = []
        paths = []

        for point in points:
            i2, j2 = point
            # x2, y2 = self.pointtool.to_coords(i2, j2)

            path, cost = self.pointtool.trace_over_image((i1, j1), (i2, j2))
            costs.append(cost)
            paths.append(path)

        min_cost = min(costs)
        min_cost_index = costs.index(min_cost)

        best_point = points[min_cost_index]
        best_path = paths[min_cost_index]
        i, j = best_point
        x, y = self.pointtool.to_coords(i, j)
        self.pseudo_anchors.append((x, y, i, j))

        return best_path


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

    def finished(self, result):
        '''
        Call callback function if self.run was successful
        '''

        if result:
            vlayer = self.vlayer
            self.pointtool.draw_path(self.path, vlayer, was_tracing=True)
            x, y, i, j = self.pseudo_anchors[-1]
            self.pointtool.add_anchor_points(x, y, i, j)
            self.pointtool.pan(x, y)
            self.pointtool.redraw()
            self.pointtool.update_rubber_band()


    def cancel(self):
        '''
        Executed when run catches cancel signal.
        Terminates the QgsTask.
        '''

        super().cancel()
