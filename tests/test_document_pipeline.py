"""Regression checks use synthetic documents and temporary working folders only."""

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz
from PIL import Image

from backend.engines import image_converter_engine as converter
from backend.engines import pdf_compiler_engine as compiler


def pdf_bytes(pages=1):
    with fitz.open() as doc:
        for number in range(pages):
            page = doc.new_page(width=80 + number, height=100)
            page.insert_text((5, 20), f"Page {number + 1}", fontsize=8)
        return doc.tobytes()


def image_bytes(format="PNG", mode="RGB", color="white", exif=None):
    buffer = io.BytesIO()
    with Image.new(mode, (40, 60), color) as image:
        image.save(buffer, format=format, **({"exif": exif} if exif else {}))
    return buffer.getvalue()


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.pages = self.root / "pages"
        self.pages.mkdir()
        self.output = self.root / "output.pdf"

    def save_page(self, name="page_1.png", width=40):
        path = self.pages / name
        with Image.new("RGB", (width, 60), "white") as image:
            image.save(path)
        return path

    def test_shorter_pdf_removes_old_tail_but_preserves_unrelated_files(self):
        converter.convert_pdf_to_images(pdf_bytes(3), self.pages)
        unrelated = self.pages / "personal.txt"
        unrelated.write_text("keep")
        self.assertEqual(converter.convert_pdf_to_images(pdf_bytes(1), self.pages), ["page_1.png"])
        self.assertEqual(sorted(p.name for p in self.pages.iterdir()), ["page_1.png", "personal.txt"])
        self.assertEqual(unrelated.read_text(), "keep")

    def test_damaged_pdf_preserves_working_document(self):
        old = self.save_page().read_bytes()
        with self.assertRaises(ValueError):
            converter.convert_pdf_to_images(b"%PDF bad data", self.pages)
        self.assertEqual((self.pages / "page_1.png").read_bytes(), old)
        self.assertEqual(list(self.root.glob(".transfiler-*")), [])

    def test_render_failure_preserves_all_old_pages(self):
        old = self.save_page().read_bytes()
        with patch.object(fitz.Page, "get_pixmap", side_effect=RuntimeError("render failed")):
            with self.assertRaises(RuntimeError):
                converter.convert_pdf_to_images(pdf_bytes(), self.pages)
        self.assertEqual((self.pages / "page_1.png").read_bytes(), old)

    def test_failed_publish_restores_previous_document(self):
        old = self.save_page().read_bytes()
        self.save_page("page_2.png")
        real_replace = converter.os.replace

        def fail_new_page(source, target):
            if Path(source).parent.name.startswith(".transfiler-upload-") and Path(source).name == "page_2.png":
                raise OSError("simulated disk error")
            return real_replace(source, target)

        with patch.object(converter.os, "replace", side_effect=fail_new_page):
            with self.assertRaises(OSError):
                converter.convert_pdf_to_images(pdf_bytes(2), self.pages)
        self.assertEqual((self.pages / "page_1.png").read_bytes(), old)
        self.assertTrue((self.pages / "page_2.png").is_file())

    def test_encrypted_pdf_is_rejected_before_replacing_pages(self):
        old = self.save_page().read_bytes()
        with fitz.open(stream=pdf_bytes(), filetype="pdf") as doc:
            encrypted = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
        with self.assertRaisesRegex(ValueError, "Password"):
            converter.convert_pdf_to_images(encrypted, self.pages)
        self.assertEqual((self.pages / "page_1.png").read_bytes(), old)

    def test_failed_rollback_keeps_recovery_pages(self):
        old = self.save_page().read_bytes()
        real_replace = converter.os.replace

        def fail_publish_and_restore(source, target):
            if Path(source).parent.name.startswith((".transfiler-upload-", ".transfiler-backup-")):
                raise OSError("simulated persistent disk failure")
            return real_replace(source, target)

        with patch.object(converter.os, "replace", side_effect=fail_publish_and_restore):
            with self.assertRaisesRegex(RuntimeError, "Recovery pages"):
                converter.convert_pdf_to_images(pdf_bytes(), self.pages)
        backups = list(self.root.glob(".transfiler-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "page_1.png").read_bytes(), old)

    def test_png_and_jpeg_become_editable_pages(self):
        for format in ["PNG", "JPEG"]:
            with self.subTest(format=format):
                self.assertEqual(converter.convert_image_to_pages(image_bytes(format), self.pages), ["page_1.png"])
                with Image.open(self.pages / "page_1.png") as page:
                    self.assertEqual(page.format, "PNG")
                    self.assertEqual(page.mode, "RGB")
                    self.assertEqual(page.size, (40, 60))

    def test_transparent_png_has_white_background(self):
        converter.convert_image_to_pages(image_bytes(mode="RGBA", color=(0, 0, 0, 0)), self.pages)
        with Image.open(self.pages / "page_1.png") as page:
            self.assertEqual(page.getpixel((0, 0)), (255, 255, 255))

    def test_jpeg_exif_orientation_is_applied(self):
        exif = Image.Exif()
        exif[274] = 6
        converter.convert_image_to_pages(image_bytes("JPEG", exif=exif), self.pages)
        with Image.open(self.pages / "page_1.png") as page:
            self.assertEqual(page.size, (60, 40))

    def test_damaged_image_keeps_old_pages(self):
        old = self.save_page().read_bytes()
        with self.assertRaises(ValueError):
            converter.convert_image_to_pages(b"\x89PNG\r\n\x1a\nwrong", self.pages)
        self.assertEqual((self.pages / "page_1.png").read_bytes(), old)

    def test_compiler_orders_numerically_and_ignores_unrelated_names(self):
        for number in [10, 2, 1]:
            self.save_page(f"page_{number}.png", width=40 + number)
        self.save_page("cover.png")
        (self.pages / "page_99.png").mkdir()
        compiler.compile_images_to_pdf(self.pages, self.output)
        with fitz.open(self.output) as doc:
            self.assertEqual([round(page.rect.width) for page in doc], [41, 42, 50])

    def test_empty_compile_preserves_old_output(self):
        self.output.write_bytes(b"old output")
        with self.assertRaises(compiler.NoImagesError):
            compiler.compile_images_to_pdf(self.pages, self.output)
        self.assertEqual(self.output.read_bytes(), b"old output")

    def test_corrupt_page_preserves_output_and_closes_images(self):
        first = self.save_page()
        (self.pages / "page_2.png").write_bytes(b"not an image")
        self.output.write_bytes(b"old output")
        with self.assertRaises(OSError):
            compiler.compile_images_to_pdf(self.pages, self.output)
        self.assertEqual(self.output.read_bytes(), b"old output")
        first.unlink()  # Also checks the input file handle is released on Windows.

    def test_failed_pdf_save_preserves_output_and_removes_temporary_file(self):
        self.save_page()
        self.output.write_bytes(b"old output")
        with patch.object(Image.Image, "save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                compiler.compile_images_to_pdf(self.pages, self.output)
        self.assertEqual(self.output.read_bytes(), b"old output")
        self.assertEqual(list(self.root.glob(".transfiler-*")), [])


if __name__ == "__main__":
    unittest.main()
