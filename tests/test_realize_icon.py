import unittest
from types import SimpleNamespace

from functions import realize_icon


class RealizeIconTests(unittest.TestCase):
    def test_uploads_first_then_scales_the_returned_texture(self):
        texture = SimpleNamespace(width=16, height=16)
        image = SimpleNamespace(get_texture=lambda: texture)

        result = realize_icon(image, 22, 22)

        self.assertIs(result, texture)
        self.assertEqual(texture.width, 22)
        self.assertEqual(texture.height, 22)
        # the raw image must never carry scaled dimensions: pyglet would
        # upload the pixel buffer with them and read past its end
        self.assertFalse(hasattr(image, "width"))
        self.assertFalse(hasattr(image, "height"))

    def test_leaves_texture_dimensions_untouched_when_not_given(self):
        texture = SimpleNamespace(width=16, height=16)
        image = SimpleNamespace(get_texture=lambda: texture)

        result = realize_icon(image)

        self.assertIs(result, texture)
        self.assertEqual(texture.width, 16)
        self.assertEqual(texture.height, 16)


if __name__ == "__main__":
    unittest.main()
