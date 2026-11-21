import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import *

class Frustum:
    """
    Extracts and tests against the view frustum.
    Exact translation of RubyDung's Frustum.java.
    """
    CULLING_MARGIN = 0.5

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

        # Normalize all six planes in one pass.  The previous loop issued a
        # NumPy call per plane; this is one vector operation for the frame.
        magnitudes = np.sqrt(np.sum(self.planes[:, :3] ** 2, axis=1))
        nonzero = magnitudes != 0
        if np.any(nonzero):
            self.planes[nonzero] /= magnitudes[nonzero, None]

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
            if (plane[0] * x + plane[1] * y + plane[2] * z + plane[3]
                    < -self.CULLING_MARGIN):
                return False
        return True

    def cube_in_frustum_batch(self, bounds):
        """Cull many AABBs at once.

        ``bounds`` is an ``(N, 6)`` array of ``(x0, y0, z0, x1, y1, z1)``.
        Returns a boolean array with one entry per box.  This replaces the
        per-chunk Python plane loop in the renderer with a handful of NumPy
        operations, which is especially noticeable at large render distances.
        """
        bounds = np.asarray(bounds, dtype=np.float32)
        if bounds.size == 0:
            return np.zeros(0, dtype=bool)
        if bounds.ndim == 1:
            bounds = bounds.reshape(1, 6)

        planes = self.planes
        # For each plane pick the AABB corner farthest along the plane normal.
        positive = planes[:, :3] >= 0.0
        x = np.where(positive[None, :, 0], bounds[:, 3][:, None],
                     bounds[:, 0][:, None])
        y = np.where(positive[None, :, 1], bounds[:, 4][:, None],
                     bounds[:, 1][:, None])
        z = np.where(positive[None, :, 2], bounds[:, 5][:, None],
                     bounds[:, 2][:, None])
        distances = (x * planes[None, :, 0]
                     + y * planes[None, :, 1]
                     + z * planes[None, :, 2]
                     + planes[None, :, 3])
        return np.all(distances >= -self.CULLING_MARGIN, axis=1)
