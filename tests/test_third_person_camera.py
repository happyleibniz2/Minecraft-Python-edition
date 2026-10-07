"""Regression: third-person camera transform math from Player.updateView.

Mirrors the GL call order exactly: pullback translate first, then rotations,
then -position (the convention verified against a live OpenGL context).
"""
import math
import unittest

import numpy as np


def _rx(degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1.0]])


def _ry(degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1.0]])


def _translate(x, y, z):
    m = np.identity(4)
    m[0, 3] = x
    m[1, 3] = y
    m[2, 3] = z
    return m


def _view_matrix(rotation, camera_type, distance=4.0):
    """Mirrors Player.updateView: T(-back) first, then rotations, then -pos."""
    pitch, yaw = rotation
    if camera_type == 2:
        back = distance
    elif camera_type == 3:
        pitch, yaw, back = -pitch, yaw + 180.0, distance
    else:
        back = 0.0
    player_pos = np.array([10.0, 70.0, 5.0])
    matrix = np.identity(4)
    if back:
        matrix = matrix @ _translate(0, 0, -back)
    matrix = matrix @ _rx(pitch) @ _ry(yaw) @ _translate(*-player_pos)
    return matrix, player_pos


class ThirdPersonCameraMatrixTests(unittest.TestCase):
    def test_rear_view_places_camera_behind_player(self):
        matrix, player_pos = _view_matrix([0.0, 0.0], 2)
        camera = (np.linalg.inv(matrix) @ np.array([0.0, 0.0, 0.0, 1.0]))[:3]
        view_of_player = matrix @ np.array([*player_pos[:3], 1.0])
        self.assertAlmostEqual(camera[2], player_pos[2] + 4.0)
        self.assertLess(view_of_player[2], 0.0)

    def test_rear_view_follows_yaw(self):
        matrix, player_pos = _view_matrix([0.0, 90.0], 2)
        camera = (np.linalg.inv(matrix) @ np.array([0.0, 0.0, 0.0, 1.0]))[:3]
        view_of_player = matrix @ np.array([*player_pos[:3], 1.0])
        self.assertAlmostEqual(camera[0], player_pos[0] - 4.0)
        self.assertLess(view_of_player[2], 0.0)

    def test_front_view_mirrors_and_sees_player(self):
        matrix, player_pos = _view_matrix([0.0, 0.0], 3)
        camera = (np.linalg.inv(matrix) @ np.array([0.0, 0.0, 0.0, 1.0]))[:3]
        view_of_player = matrix @ np.array([*player_pos[:3], 1.0])
        self.assertAlmostEqual(camera[2], player_pos[2] - 4.0)
        self.assertLess(view_of_player[2], 0.0)  # camera looks back at player

    def test_first_person_is_untouched(self):
        matrix, player_pos = _view_matrix([15.0, -35.0], 1)
        camera = (np.linalg.inv(matrix) @ np.array([0.0, 0.0, 0.0, 1.0]))[:3]
        self.assertTrue(np.allclose(camera, player_pos[:3]))


if __name__ == "__main__":
    unittest.main()
