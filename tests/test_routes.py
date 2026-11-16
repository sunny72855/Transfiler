import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from PIL import Image

import app as application
from backend.utils import path as page_paths


def sample_image():
    buffer = io.BytesIO()
    with Image.new("RGB", (80, 80), "white") as image:
        image.save(buffer, format="PNG")
    return buffer.getvalue()


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.pages = self.root / "saved_pages"
        self.pages.mkdir()
        self.output = self.root / "output.pdf"
        for target, name, value in [
            (application, "SAVED_PAGES_DIR", self.pages),
            (application, "OUTPUT_PDF", self.output),
            (page_paths, "SAVED_PAGES_DIR", self.pages),
        ]:
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(application.app)
        self.addCleanup(self.client.close)
        self.payload = {"x": 5, "y": 5, "secondX": 70, "secondY": 50, "image-dir": "/saved_pages/page_1.png?t=123"}

    def upload(self):
        response = self.client.post("/uploadfiles/", files={"file": ("test.png", sample_image(), "image/png")})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def test_image_upload_returns_editor_contract_and_compiles(self):
        self.assertEqual(self.upload().json(), {"images": ["page_1.png"]})
        response = self.client.post("/compilepdf/")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertEqual(self.output.read_bytes(), response.content)

    def test_fake_filename_no_longer_bypasses_type_check(self):
        response = self.client.post("/uploadfiles/", files={"file": ("kien.pdf", b"not pdf", "application/pdf")})
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.json()["detail"]["code"], "UNSUPPORTED_FILE")

    def test_damaged_upload_has_actionable_error_and_preserves_page(self):
        self.upload()
        previous = (self.pages / "page_1.png").read_bytes()
        response = self.client.post("/uploadfiles/", files={"file": ("bad.pdf", b"%PDF bad", "application/pdf")})
        self.assertEqual(response.status_code, 422)
        self.assertEqual((self.pages / "page_1.png").read_bytes(), previous)

    def test_empty_compile_rejects_old_output(self):
        self.output.write_bytes(b"stale")
        response = self.client.post("/compilepdf/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["code"], "NO_IMAGES")
        self.assertEqual(self.output.read_bytes(), b"stale")

    def test_clear_preserves_unrelated_files_and_empty_repeat_works(self):
        self.upload()
        unrelated = self.pages / "keep.txt"
        unrelated.write_text("keep")
        self.assertEqual(self.client.delete("/deletefiles/").status_code, 200)
        self.assertFalse((self.pages / "page_1.png").exists())
        self.assertEqual(unrelated.read_text(), "keep")
        self.assertIn("0 files", self.client.delete("/deletefiles/").json()["message"])

    def test_valid_crop_runs_real_image_edit(self):
        self.upload()
        with patch.object(application, "run_ocr_on_bytes", return_value="Sewing"), patch.object(application, "translate_text", new=AsyncMock(return_value="Đường may")):
            response = self.client.post("/cropimage/", json=self.payload)
        self.assertEqual(response.status_code, 200, response.text)
        with Image.open(self.pages / "page_1.png") as page:
            self.assertEqual(page.getpixel((5, 5)), (0, 0, 0))
            self.assertEqual(page.getpixel((0, 0)), (255, 255, 255))

    def test_blank_ocr_never_calls_translation_or_edits(self):
        self.upload()
        previous = (self.pages / "page_1.png").read_bytes()
        with patch.object(application, "run_ocr_on_bytes", return_value=" \n"), patch.object(application, "translate_text", new=AsyncMock()) as translate:
            response = self.client.post("/cropimage/", json=self.payload)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "NO_TEXT")
        translate.assert_not_awaited()
        self.assertEqual((self.pages / "page_1.png").read_bytes(), previous)

    def test_empty_translation_does_not_edit(self):
        self.upload()
        previous = (self.pages / "page_1.png").read_bytes()
        with patch.object(application, "run_ocr_on_bytes", return_value="Sewing"), patch.object(application, "translate_text", new=AsyncMock(return_value="")):
            response = self.client.post("/cropimage/", json=self.payload)
        self.assertEqual(response.status_code, 502)
        self.assertEqual((self.pages / "page_1.png").read_bytes(), previous)

    def test_translation_failure_does_not_edit_and_releases_guard(self):
        self.upload()
        previous = (self.pages / "page_1.png").read_bytes()
        with patch.object(application, "run_ocr_on_bytes", return_value="Sewing"), patch.object(application, "translate_text", new=AsyncMock(side_effect=RuntimeError("service failed"))):
            with self.assertLogs("app", level="ERROR"):
                response = self.client.post("/cropimage/", json=self.payload)
        self.assertEqual(response.status_code, 503)
        self.assertEqual((self.pages / "page_1.png").read_bytes(), previous)
        self.assertEqual(self.client.post("/compilepdf/").status_code, 200)

    def test_missing_page_and_unsafe_paths_are_errors(self):
        self.assertEqual(self.client.post("/cropimage/", json=self.payload).status_code, 404)
        for value in ["../image.png", "/saved_pages/../image.png", "C:/Windows/system.ini", "/saved_pages/%2e%2e/image.png"]:
            with self.subTest(path=value):
                response = self.client.post("/cropimage/", json={**self.payload, "image-dir": value})
                self.assertEqual(response.status_code, 422, response.text)

    def test_out_of_bounds_or_reversed_crop_rejected_before_ocr(self):
        self.upload()
        with patch.object(application, "run_ocr_on_bytes") as ocr:
            for updates in [{"x": -1}, {"x": 72}, {"secondX": 500}, {"secondY": 5}]:
                with self.subTest(updates=updates):
                    response = self.client.post("/cropimage/", json={**self.payload, **updates})
                    self.assertEqual(response.status_code, 422, response.text)
            ocr.assert_not_called()

    def test_busy_requests_rejected_without_touching_pages(self):
        self.upload()
        previous = (self.pages / "page_1.png").read_bytes()
        application._document_lock.acquire()
        try:
            responses = [self.client.delete("/deletefiles/"), self.client.post("/compilepdf/"), self.client.post("/cropimage/", json=self.payload), self.client.post("/uploadfiles/", files={"file": ("test.png", sample_image())})]
        finally:
            application._document_lock.release()
        self.assertEqual([response.status_code for response in responses], [409] * 4)
        self.assertEqual((self.pages / "page_1.png").read_bytes(), previous)

    def test_pending_translation_prevents_clear_or_upload_from_another_client(self):
        self.upload()
        entered = threading.Event()
        release = threading.Event()

        async def translate(text):
            entered.set()
            for _ in range(500):
                if release.is_set():
                    return "May"
                await asyncio.sleep(0.01)
            raise RuntimeError("test timed out")

        def crop_request():
            with TestClient(application.app) as client:
                return client.post("/cropimage/", json=self.payload)

        with patch.object(application, "run_ocr_on_bytes", return_value="Sewing"), patch.object(application, "translate_text", side_effect=translate), ThreadPoolExecutor(max_workers=1) as executor:
            request = executor.submit(crop_request)
            try:
                self.assertTrue(entered.wait(timeout=5))
                self.assertEqual(self.client.delete("/deletefiles/").status_code, 409)
                self.assertEqual(self.client.post("/uploadfiles/", files={"file": ("new.png", sample_image())}).status_code, 409)
            finally:
                release.set()
            self.assertEqual(request.result(timeout=5).status_code, 200)

    def test_file_response_has_immutable_snapshot_and_cleanup(self):
        self.upload()
        response = application._compile_response()
        snapshot = Path(response.path)
        try:
            self.assertNotEqual(snapshot, self.output)
            expected = snapshot.read_bytes()
            self.output.write_bytes(b"new output")
            self.assertEqual(snapshot.read_bytes(), expected)
        finally:
            asyncio.run(self.call_snapshot(response))
        self.assertFalse(snapshot.exists())

    async def call_snapshot(self, response, headers=(), fail_send=False):
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if fail_send:
                raise OSError("client disconnected")
            messages.append(message)

        await response({"type": "http", "method": "GET", "headers": headers}, receive, send)
        return messages

    def test_invalid_ranges_and_disconnect_still_clean_up_pdf_snapshot(self):
        self.upload()
        for header, status in [(b"nonsense", 400), (b"bytes=9999999999-", 416)]:
            with self.subTest(header=header):
                response = application._compile_response()
                snapshot = Path(response.path)
                messages = asyncio.run(self.call_snapshot(response, [(b"range", header)]))
                self.assertEqual(messages[0]["status"], status)
                self.assertFalse(snapshot.exists())
        response = application._compile_response()
        snapshot = Path(response.path)
        with self.assertRaises(OSError):
            asyncio.run(self.call_snapshot(response, fail_send=True))
        self.assertFalse(snapshot.exists())

    def test_startup_from_another_directory_does_not_initialize_models(self):
        program = "import sys; sys.path.insert(0, sys.argv[1]); import app; assert 'paddleocr' not in sys.modules; print('startup ok')"
        result = subprocess.run([sys.executable, "-c", program, str(application.PROJECT_ROOT)], cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("startup ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
