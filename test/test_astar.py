import unittest
from astar import heuristic

class TestHeuristicFunction(unittest.TestCase):

    def test_heuristic_same_point(self):
        self.assertEqual(heuristic((0, 0), (0, 0)), 0)

    def test_heuristic_horizontal(self):
        self.assertEqual(heuristic((0, 0), (5, 0)), 5)

    def test_heuristic_vertical(self):
        self.assertEqual(heuristic((0, 0), (0, 5)), 5)

    def test_heuristic_diagonal(self):
        self.assertEqual(heuristic((0, 0), (3, 4)), 7)

    def test_heuristic_negative_coordinates(self):
        self.assertEqual(heuristic((0, 0), (-3, -4)), 7)

    def test_heuristic_mixed_coordinates(self):
        self.assertEqual(heuristic((2, -3), (-1, 1)), 7)

if __name__ == '__main__':
    unittest.main()
