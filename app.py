"""FastAPI routes for the single shared working document."""

from contextlib import contextmanager
import logging
from pathlib import Path
import shutil
import tempfile
from threading import Lock

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from backend.common.common_schemas import CropData
from backend.engines.image_converter_engine import convert_image_to_pages, convert_pdf_to_images
from backend.engines.image_manipulation_engine import crop_images, edit_image
from backend.engines.ocr_engine import run_ocr_on_bytes
from backend.engines.pdf_compiler_engine import NoImagesError, compile_images_to_pdf
from backend.engines.translation_engine import translate_text
from backend.utils.pages import saved_page_paths

PROJECT_ROOT = Path(__file__).resolve().parent
SAVED_PAGES_DIR = PROJECT_ROOT / "saved_pages"
OUTPUT_PDF = PROJECT_ROOT / "output.pdf"
SAVED_PAGES_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger(__name__)
# All clients share the same document. Reject conflicting operations, including
# from other tabs, while an OCR/translation request is awaiting the external API.
_document_lock = Lock()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@contextmanager
def _document_operation():
    if not _document_lock.acquire(blocking=False):
        raise _error(409, "DOCUMENT_BUSY", "Another document operation is running. Please wait and try again.")
    try:
        yield
    except NoImagesError as error:
        raise _error(400, "NO_IMAGES", str(error)) from error
    except FileNotFoundError as error:
        raise _error(404, "PAGE_NOT_FOUND", "The selected page no longer exists. Please upload or select a page again.") from error
    except ValueError as error:
        raise _error(422, "INVALID_INPUT", str(error)) from error
    except (OSError, RuntimeError) as error:
        logger.exception("Document operation failed")
        raise _error(503, "PROCESSING_FAILED", "The document could not be processed. Check the server configuration and try again.") from error
    finally:
        _document_lock.release()


@app.post("/uploadfiles/")
async def upload_file(file: UploadFile = File(...)):
    try:
        with _document_operation():
            content = await file.read()
            if content.startswith(b"%PDF"):
                converter = convert_pdf_to_images
            elif content.startswith(b"\x89PNG\r\n\x1a\n") or content.startswith(b"\xff\xd8\xff"):
                converter = convert_image_to_pages
            else:
                raise _error(415, "UNSUPPORTED_FILE", "Please upload a PDF, PNG, or JPG.")
            images = await run_in_threadpool(converter, content, str(SAVED_PAGES_DIR))
            return {"images": images}
    finally:
        await file.close()


class _SnapshotResponse(FileResponse):
    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # FileResponse background tasks can be skipped by invalid Range
            # responses or a disconnected client. Always release our snapshot.
            await run_in_threadpool(Path(self.path).unlink, missing_ok=True)


def _compile_response():
    output_path = compile_images_to_pdf(str(SAVED_PAGES_DIR), str(OUTPUT_PDF))
    # FileResponse streams after the route returns. Give each response its own
    # snapshot so another compile cannot change bytes while they are being sent.
    snapshot = None
    try:
        with tempfile.NamedTemporaryFile(prefix="transfiler-download-", suffix=".pdf", delete=False) as temporary:
            snapshot = Path(temporary.name)
        shutil.copyfile(output_path, snapshot)
        return _SnapshotResponse(
            snapshot, media_type="application/pdf", filename="output.pdf",
        )
    except Exception:
        if snapshot is not None:
            snapshot.unlink(missing_ok=True)
        raise


@app.post("/compilepdf/")
async def compile_pdf():
    with _document_operation():
        return await run_in_threadpool(_compile_response)


def _delete_pages():
    pages = saved_page_paths(SAVED_PAGES_DIR)
    for page in pages:
        page.unlink()
    return {"message": f"Successfully deleted {len(pages)} files!"}


@app.delete("/deletefiles/")
async def delete_files():
    with _document_operation():
        return await run_in_threadpool(_delete_pages)


@app.post("/cropimage/")
async def process_crop(data: CropData):
    with _document_operation():
        image_bytes = await run_in_threadpool(crop_images, data)
        detected_text = await run_in_threadpool(run_ocr_on_bytes, image_bytes)
        if not detected_text or not detected_text.strip():
            raise _error(422, "NO_TEXT", "No text was found in the selection. Select a text region and try again.")
        translated_text = await translate_text(detected_text)
        if not translated_text or not translated_text.strip():
            raise _error(502, "EMPTY_TRANSLATION", "Translation returned no text. The page has not been changed.")
        await run_in_threadpool(edit_image, data, translated_text)
        return {"status": "success", "message": "Image cropped successfully"}


# Keep the generated-image mount before the catch-all frontend mount.
app.mount("/saved_pages", StaticFiles(directory=SAVED_PAGES_DIR), name="images")
app.mount("/", StaticFiles(directory=PROJECT_ROOT / "static", html=True), name="static")
