import asyncio
import io
import os
from pathlib import Path
import tempfile
import types
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from PIL import Image, ImageChops, ImageDraw
from pydantic import ValidationError

from backend.common.common_schemas import CropData
from backend.engines import image_manipulation_engine as images
from backend.engines import ocr_engine as ocr
from backend.engines import translation_engine as translation
from backend.utils import path as paths


def crop_data(**overrides):
    values = {"x": 10.2, "y": 12.4, "secondX": 149.8, "secondY": 95.1,
              "image-dir": "/saved_pages/page_1.png?t=123"}
    values.update(overrides)
    return CropData(**values)


class CropValidationTests(unittest.TestCase):
    def test_invalid_coordinates_are_rejected(self):
        for values in ({"x": -1}, {"y": float("nan")}, {"secondY": float("inf")},
                       {"secondX": 0}, {"secondY": 0}, {"secondX": 10.2},
                       {"image-dir": ""}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                crop_data(**values)

    def test_fractional_coordinates_are_accepted(self):
        self.assertEqual(crop_data().x, 10.2)


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.pages = self.root / "saved_pages"
        self.pages.mkdir()
        self.page = self.pages / "page_1.png"
        with Image.new("RGB", (180, 120), (19, 79, 139)) as image:
            image.save(self.page)
        self.path_patch = patch.object(paths, "SAVED_PAGES_DIR", self.pages)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.directory.cleanup()

    def test_url_and_cache_query_resolve_to_saved_page(self):
        for value in ("/saved_pages/page_1.png?t=2", "saved_pages/page_1.png",
                      "http://localhost:8000/saved_pages/page_1.png?t=7",
                      "https://example.com/saved_pages/page%5F1.png"):
            with self.subTest(value=value):
                self.assertEqual(paths.safe_resolve_path(value), self.page.resolve())

    def test_path_escape_and_other_files_rejected(self):
        values = ["/saved_pages/../README.md", "../saved_pages/page_1.png",
                  "/saved_pages/%2e%2e/secret.png", "/saved_pages/..%5Csecret.png",
                  "C:\\secret.png", "/saved_pages/page_1.jpg", "/backend/.env",
                  "file:///saved_pages/page_1.png", "/saved_pages/subdir/page_1.png",
                  "/saved_pages/page_1.png:extra.png", "/saved_pages/x%00.png",
                  "/saved_pages/page_0.png", "/saved_pages/page_01.png", "/saved_pages/other.png"]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                paths.safe_resolve_path(value)

    def test_symlink_escape_rejected(self):
        outside = self.root / "outside.png"
        outside.write_bytes(b"outside")
        linked = self.pages / "page_2.png"
        try:
            linked.symlink_to(outside)
        except OSError:
            self.skipTest("This account cannot create file symlinks.")
        with self.assertRaises(ValueError):
            paths.safe_resolve_path("/saved_pages/page_2.png")

    def test_crop_and_edit_share_fractional_pixel_bounds(self):
        data = crop_data()
        with Image.open(io.BytesIO(images.crop_images(data))) as cropped:
            self.assertEqual(cropped.size, (140, 84))
        images.edit_image(data, "Đường may\nKích thước")
        with Image.open(self.page) as edited:
            self.assertEqual(edited.getpixel((10, 12)), (0, 0, 0))
            self.assertEqual(edited.getpixel((150, 96)), (19, 79, 139))

    def test_drawing_changes_no_pixels_outside_selection(self):
        before = Image.open(self.page).convert("RGB")
        images.edit_image(crop_data(), "Đường may\nKích thước")
        with Image.open(self.page) as after:
            changes = ImageChops.difference(before, after).getbbox()
            self.assertIsNotNone(changes)
            self.assertGreaterEqual(changes[0], 10)
            self.assertGreaterEqual(changes[1], 12)
            self.assertLessEqual(changes[2], 150)
            self.assertLessEqual(changes[3], 96)
            self.assertEqual(changes, (10, 12, 150, 96))
        before.close()

    def test_vietnamese_multiline_glyphs_fit_measured_bounds(self):
        with Image.new("RGB", (180, 120)) as image:
            draw = ImageDraw.Draw(image)
            text = "Đường may\nKích thước"
            size = images.get_font_size(draw, (0, 0), (140, 84), text)
            bbox = draw.multiline_textbbox((0, 0), text, font=images._font(size), spacing=0)
            self.assertLessEqual(bbox[2] - bbox[0], 140)
            self.assertLessEqual(bbox[3] - bbox[1], 84)

    def test_invalid_bounds_and_empty_text_preserve_original(self):
        before = self.page.read_bytes()
        for values in ({"secondX": 181}, {"secondY": 121},
                       {"x": 180, "secondX": 180.0000001}):
            data = crop_data(**values)
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    images.crop_images(data)
                with self.assertRaises(ValueError):
                    images.edit_image(data, "text")
                self.assertEqual(self.page.read_bytes(), before)
        with self.assertRaises(ValueError):
            images.edit_image(crop_data(), " ")
        self.assertEqual(self.page.read_bytes(), before)

    def test_missing_image_is_an_error(self):
        data = crop_data(**{"image-dir": "/saved_pages/page_99.png"})
        with self.assertRaises(FileNotFoundError):
            images.edit_image(data, "text")

    def test_write_failure_preserves_original_and_cleans_temporary_file(self):
        before = self.page.read_bytes()
        with patch.object(Image.Image, "save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                images.edit_image(crop_data(), "Đường may")
        self.assertEqual(self.page.read_bytes(), before)
        self.assertEqual(list(self.pages.iterdir()), [self.page])

    def test_missing_unicode_font_preserves_original(self):
        before = self.page.read_bytes()
        with patch.dict(os.environ, {"TRANSFILER_FONT": str(self.root / "missing.ttf")}):
            with self.assertRaises(RuntimeError):
                images.edit_image(crop_data(), "Đường may")
        self.assertEqual(self.page.read_bytes(), before)

    def test_impossibly_small_selection_preserves_original(self):
        before = self.page.read_bytes()
        data = crop_data(x=0, y=0, secondX=1, secondY=1)
        with self.assertRaises(ValueError):
            images.edit_image(data, "very long text" * 100)
        self.assertEqual(self.page.read_bytes(), before)


class OCRTests(unittest.TestCase):
    def setUp(self):
        with Image.new("RGB", (20, 20), "white") as image, io.BytesIO() as buffer:
            image.save(buffer, "PNG")
            self.png = buffer.getvalue()

    def test_no_detections_returns_empty_text(self):
        for result in (None, [], [None], [[]]):
            with self.subTest(result=result), patch.object(ocr, "_get_ocr", return_value=Mock(ocr=Mock(return_value=result))):
                self.assertEqual(ocr.run_ocr_on_bytes(self.png), "")

    def test_invalid_image_does_not_initialize_model(self):
        with patch.object(ocr, "_get_ocr") as model:
            for content in (b"", b"not an image"):
                with self.assertRaises(ValueError):
                    ocr.run_ocr_on_bytes(content)
            model.assert_not_called()

    def test_recognized_lines_are_joined_in_order(self):
        result = [[[[0, 0], ("Seam", 0.9)], [[0, 1], ("Length", 0.8)]]]
        with patch.object(ocr, "_get_ocr", return_value=Mock(ocr=Mock(return_value=result))):
            self.assertEqual(ocr.run_ocr_on_bytes(self.png), "Seam\nLength")

    def test_inference_failure_becomes_runtime_error(self):
        with patch.object(ocr, "_get_ocr", return_value=Mock(ocr=Mock(side_effect=ValueError("predictor failed")))):
            with self.assertRaises(RuntimeError):
                ocr.run_ocr_on_bytes(self.png)

    def test_model_is_initialized_once_and_failed_startup_is_retryable(self):
        predictor = Mock()
        constructor = Mock(side_effect=[OSError("unavailable model"), predictor])
        module = types.ModuleType("paddleocr")
        module.PaddleOCR = constructor
        with patch.dict("sys.modules", {"paddleocr": module}), patch.object(ocr, "_ocr", None):
            with self.assertRaises(RuntimeError):
                ocr._get_ocr()
            self.assertIsNone(ocr._ocr)
            self.assertIs(ocr._get_ocr(), predictor)
            self.assertIs(ocr._get_ocr(), predictor)
        self.assertEqual(constructor.call_count, 2)
        self.assertTrue(constructor.call_args.kwargs["use_angle_cls"])


class TranslationTests(unittest.TestCase):
    def test_blank_input_does_not_create_client(self):
        with patch.object(translation, "_get_client") as get_client:
            with self.assertRaises(ValueError):
                asyncio.run(translation.translate_text(" \n"))
            get_client.assert_not_called()

    def test_async_success_and_configured_model(self):
        generate = AsyncMock(return_value=SimpleNamespace(text="Đường may"))
        client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
        with patch.object(translation, "_get_client", return_value=client), patch.dict(os.environ, {"GEMINI_MODEL": "test-model"}):
            self.assertEqual(asyncio.run(translation.translate_text("Seam")), "Đường may")
        generate.assert_awaited_once()
        self.assertEqual(generate.call_args.kwargs["model"], "test-model")

    def test_empty_blocked_and_failed_responses_raise(self):
        for value in (None, "", " \n", OSError("network down")):
            generate = AsyncMock(side_effect=value) if isinstance(value, Exception) else AsyncMock(return_value=SimpleNamespace(text=value))
            client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
            with self.subTest(value=value), patch.object(translation, "_get_client", return_value=client):
                with self.assertRaises(RuntimeError):
                    asyncio.run(translation.translate_text("Seam"))

    def test_missing_key_is_retryable_without_creating_client(self):
        with patch.object(translation, "_client", None), patch("dotenv.load_dotenv"), patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                translation._get_client()
            self.assertIsNone(translation._client)

    def test_environment_root_and_legacy_settings_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "backend").mkdir()
            root_settings = root / ".env"
            root_settings.write_text("GEMINI_API_KEY=root-example\n", encoding="utf-8")
            (root / "backend" / ".env").write_text("GEMINI_API_KEY=legacy-example\n", encoding="utf-8")
            for configured, expected in (("environment-example", "environment-example"), (None, "root-example")):
                environment = {} if configured is None else {"GEMINI_API_KEY": configured}
                with self.subTest(configured=configured), patch.object(translation, "PROJECT_ROOT", root), \
                     patch.object(translation, "_client", None), patch.dict(os.environ, environment, clear=True), \
                     patch("google.genai.Client") as constructor:
                    translation._get_client()
                    constructor.assert_called_once_with(api_key=expected)
            root_settings.unlink()
            with patch.object(translation, "PROJECT_ROOT", root), patch.object(translation, "_client", None), \
                 patch.dict(os.environ, {}, clear=True), patch("google.genai.Client") as constructor:
                translation._get_client()
                constructor.assert_called_once_with(api_key="legacy-example")


if __name__ == "__main__":
    unittest.main()
