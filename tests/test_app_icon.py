"""Catch GTK's asymmetric rounded-rectangle SVG rendering regression."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "data/icons/hicolor/scalable/apps/io.github.qwersyk.Newelle.svg"


class AppIconRenderingTests(unittest.TestCase):
    def test_gtk_matches_librsvg(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            renderer = directory / "render-icon"
            flags = shlex.split(subprocess.check_output(
                ["pkg-config", "--cflags", "--libs", "gtk4"], text=True))
            subprocess.run(["cc", str(ROOT / "tests/render_app_icon.c"), "-o", str(renderer), *flags], check=True)
            gtk_png, reference_png = directory / "gtk.png", directory / "reference.png"
            subprocess.run([str(renderer), str(ICON), str(gtk_png)], check=True)
            subprocess.run(["rsvg-convert", str(ICON), "-o", str(reference_png)], check=True)

            def composite(path):
                with Image.open(path) as image:
                    return Image.alpha_composite(Image.new("RGBA", image.size), image.convert("RGBA")).convert("RGB")

            actual, expected = composite(gtk_png), composite(reference_png)
            difference = ImageStat.Stat(ImageChops.difference(actual, expected))
            # Allow renderer antialiasing differences; the swapped corners
            # produce a much larger mean error than ordinary antialiasing.
            self.assertLess(sum(difference.mean) / 3, 0.5)
            with Image.open(gtk_png) as image:
                self.assertEqual(image.getpixel((152, 14))[3], 0, "top-right corner must stay rounded")
                self.assertGreater(image.getpixel((17, 137))[3], 240, "bottom-left corner must stay square")


if __name__ == "__main__":
    unittest.main()
