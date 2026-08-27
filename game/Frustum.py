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
        # Get matrices (column-major)
        proj = glGetFloatv(GL_PROJECTION_MATRIX)
        modl = glGetFloatv(GL_MODELVIEW_MATRIX)

        # Combine: clip = proj * modl (column-major)
        # Flatten to a 16-element array for easy indexing
        clip = np.dot(proj, modl).flatten()

        # Extract planes as in RubyDung (row-major extraction)
        # Right plane
        self.planes[0] = [clip[3] - clip[0],
                          clip[7] - clip[4],
                          clip[11] - clip[8],
                          clip[15] - clip[12]]
        # Left plane
        self.planes[1] = [clip[3] + clip[0],
                          clip[7] + clip[4],
                          clip[11] + clip[8],
                          clip[15] + clip[12]]
        # Bottom plane
        self.planes[2] = [clip[3] + clip[1],
                          clip[7] + clip[5],
                          clip[11] + clip[9],
                          clip[15] + clip[13]]
        # Top plane
        self.planes[3] = [clip[3] - clip[1],
                          clip[7] - clip[5],
                          clip[11] - clip[9],
                          clip[15] - clip[13]]
        # Back plane
        self.planes[4] = [clip[3] - clip[2],
                          clip[7] - clip[6],
                          clip[11] - clip[10],
                          clip[15] - clip[14]]
        # Front plane
        self.planes[5] = [clip[3] + clip[2],
                          clip[7] + clip[6],
                          clip[11] + clip[10],
                          clip[15] + clip[14]]

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
        corners = [
            (x0, y0, z0), (x1, y0, z0),
            (x0, y1, z0), (x1, y1, z0),
            (x0, y0, z1), (x1, y0, z1),
            (x0, y1, z1), (x1, y1, z1)
        ]

        for p in range(6):
            plane = self.planes[p]
            inside = False
            for corner in corners:
                d = plane[0]*corner[0] + plane[1]*corner[1] + plane[2]*corner[2] + plane[3]
                if d > 0:
                    inside = True
                    break
            if not inside:
                return False
        return True