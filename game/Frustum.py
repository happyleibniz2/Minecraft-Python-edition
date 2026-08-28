import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import *

class Frustum:
    """
    Extracts and tests against the view frustum.
    Exact translation of RubyDung's Frustum.java.
    """
    def __init__(self):
        self.planes = np.zeros((6, 4), dtype=np.float32)

    def extract(self):
        """
        Extract the 6 frustum planes from OpenGL's current projection
        and modelview matrices. Must be called each frame after setting
        the camera.
        """
        # PyOpenGL exposes OpenGL's column-major matrices transposed.
        proj = np.asarray(glGetFloatv(GL_PROJECTION_MATRIX), dtype=np.float32).reshape(4, 4).T
        modl = np.asarray(glGetFloatv(GL_MODELVIEW_MATRIX), dtype=np.float32).reshape(4, 4).T
        clip = np.dot(proj, modl)

        # Right plane
        self.planes[0] = clip[3] - clip[0]
        # Left plane
        self.planes[1] = clip[3] + clip[0]
        # Bottom plane
        self.planes[2] = clip[3] + clip[1]
        # Top plane
        self.planes[3] = clip[3] - clip[1]
        # Back plane
        self.planes[4] = clip[3] - clip[2]
        # Front plane
        self.planes[5] = clip[3] + clip[2]

        # Normalize each plane
        for i in range(6):
            mag = np.sqrt(self.planes[i][0]**2 + self.planes[i][1]**2 + self.planes[i][2]**2)
            if mag != 0:
                self.planes[i] /= mag

    def cube_in_frustum(self, x0, y0, z0, x1, y1, z1):
        """
        Test if an AABB (axis-aligned bounding box) is inside the frustum.
        Returns True if visible, False if culled.
        (RubyDung's cubeInFrustum method)
        """
        for plane in self.planes:
            x = x1 if plane[0] >= 0 else x0
            y = y1 if plane[1] >= 0 else y0
            z = z1 if plane[2] >= 0 else z0
            if plane[0] * x + plane[1] * y + plane[2] * z + plane[3] <= 0:
                return False
        return True
