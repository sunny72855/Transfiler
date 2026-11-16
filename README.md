# Transfiler

Current release: **Patch v0.1.1**.

A small FastAPI app for translating English garment-manufacturing PDFs/images into
Vietnamese, built around a scan → OCR → translate → re-draw → recompile workflow.

## Patch notes

### Patch v0.1.1 (2026-11-16)

This patch fixes document replacement, editable PNG/JPEG uploads, crop accuracy,
Vietnamese text placement, failed-processing data loss, conflicting operations,
and PDF output safety. It also improves startup, error messages and setup.

<details>
<summary>Read the detailed v0.1.1 changes</summary>

#### Uploads and working-document integrity

- Fixed shorter PDF uploads retaining pages from the previous document. Pages are now rendered into a temporary folder before replacing the previous numbered pages, so compiling contains only the newly uploaded document. Failed publication restores the previous pages; if a persistent filesystem failure also prevents restoration, recovery copies are retained rather than deleted. ([Converter](backend/engines/image_converter_engine.py), [page list](backend/utils/pages.py))
- PNG/JPEG uploads now produce an editable `page_1.png` and return the same page-list response as PDFs. Previously they returned OCR text, leaving the editor without pages to display. Camera orientation is applied and transparency is flattened onto white before editing/compilation.
- Removed the filename-based file-type bypass. Unsupported uploads return an HTTP error, while damaged or password-protected documents are rejected without replacing the working pages. Uploaded file handles are always closed.
- Clear now removes numbered working pages while preserving unrelated files in the folder.

#### Crop selection and page display

- Fixed crop coordinates becoming inaccurate after image pan/zoom. Selection bounds are converted from the current displayed image into original-image pixels, rather than using an old iframe-size ratio. Hidden, empty and out-of-image selections are rejected before sending a request. Rotation/skew controls are disabled because the backend edits rectangular regions. ([Cropper](static/cropper/script.js), [payload](static/utils/cropHandler.js))
- Fixed page fitting that could only shrink after switching from landscape to portrait. Page size now uses the full available stage and refits on window resize. Asynchronous loads carry revisions so an older load cannot overwrite the latest selected page. ([Page display](static/utils/imageDisplay.js), [editor](static/script.js))
- Cropper initialization is awaited before enabling selection tools, and loading failures are reported. Removed the unused Cropper.js v1 dependency from the parent page; the editor continues using its pinned v2 component implementation.
- Added supported file types to the file picker, accessible page-thumbnail buttons, and descriptive file-input/iframe labels.

#### Crop validation and safe text replacement

- Restricted editable paths to canonical numbered PNGs inside `saved_pages`. Validation decodes public image URLs/cache queries and rejects traversal, Windows separator bypasses, other file types and resolved paths outside the working folder. ([Path resolver](backend/utils/path.py))
- Rejected nonfinite, negative, reversed, empty and out-of-image crop bounds. OCR and drawing now use the same normalized integer pixel rectangle. Missing pages return an error rather than reporting a successful edit. ([Schema](backend/common/common_schemas.py), [image editor](backend/engines/image_manipulation_engine.py))
- Fixed multiline Vietnamese text and accented glyphs extending outside the selection. Font fitting measures multiline bounds and compensates for glyph offsets; the replacement rectangle no longer paints an extra row/column beyond the crop.
- Edited images are written to a temporary PNG and atomically replace the original only after a successful save. Empty text, missing fonts, impossible text fits and failed writes leave the original page intact. Unicode font fallbacks and the optional `TRANSFILER_FONT` setting replace the single hardcoded-font assumption.

#### OCR, translation and startup

- OCR now handles blank detections and invalid image data safely. The model initializes on first use instead of during app import, failed initialization can be retried, angle classification is enabled, and shared predictor calls are serialized. Upload/display/compile no longer wait for OCR initialization. ([OCR](backend/engines/ocr_engine.py))
- Failed, blocked or empty translations now stop the crop operation instead of burning an error placeholder into the image. Blank OCR also stops before translation or editing. ([Translation](backend/engines/translation_engine.py), [routes](app.py))
- Gemini initializes only when translation is requested, so a missing API key no longer prevents unrelated features from starting. Existing environment variables take precedence over root `.env` settings, then legacy `backend/.env` settings. `GEMINI_MODEL` optionally overrides the existing default model.
- Static files, working pages and output paths now resolve relative to the project rather than the shell's launch directory.

#### Requests, editor state and document operations

- Fixed requests going to the hardcoded `127.0.0.1:8000` when the editor is served on another host/port. All API calls now use the editor's origin. Upload/crop/clear/compile share HTTP error handling and preserve readable server messages. ([API](static/utils/api.js))
- Replaced separate browser busy flags with one operation guard. Conflicting actions are disabled while a request runs, failures are shown visibly, and controls are restored for retry. Clear and successful upload reset stale images/selections; failed requests preserve the existing editor state. ([Editor](static/script.js))
- Fixed thumbnail refresh targeting `page_10` when editing `page_1`, and errors when the active thumbnail is missing. Refresh now uses an exact page path and cache-busting URLs.
- Added a server-side guard across upload, clear, crop and compile. Concurrent requests from other tabs receive HTTP 409 rather than replacing pages during a pending crop. Blocking PDF/image/OCR operations use the thread pool so the server can continue serving the UI. This remains a single shared document in one server process.

#### PDF compilation

- Fixed uploaded page images returning 404 by mounting the working folder at the frontend's `/saved_pages` prefix before the catch-all frontend mount. ([Routes](app.py))
- Empty compilation now returns `NO_IMAGES` and an upload reminder, preventing server errors or accidental reuse of an old PDF.
- Compilation ignores unrelated PNG names/directories, sorts canonical numbered pages numerically, and closes image resources even when a later read/save fails. A complete temporary PDF replaces the previous output only after writing succeeds. ([Compiler](backend/engines/pdf_compiler_engine.py))
- Each PDF response streams its own immutable snapshot so another compile cannot alter an in-progress response. Snapshots are deleted after success, malformed/unsatisfiable Range requests, or sending failures. Compile PDF retains its existing behavior of compiling without starting a browser download.

#### Branding and setup

- Renamed the app header and browser tab from Document Translator to Transfiler. ([HTML](static/index.html))
- Aligned direct and transitive OpenCV pins with the existing PaddleOCR/NumPy stack, preventing a newer headless OpenCV dependency from requiring NumPy 2. ([Requirements](requirements.txt))
- Updated setup documentation for Python 3.11, explicit virtual-environment commands, the corrected image URL, editable image uploads, settings lookup, shared-document operation and regression commands. Updated the current release label to Patch v0.1.1. ([README](README.md))

#### Verification and current limits

The release checks passed 52 Python tests and 15 frontend tests. One Windows
symlink test was skipped because the account could not create symlinks. A real
cached-model OCR check recognized a synthetic English sample correctly.

Live Gemini translation, a clean dependency installation, and real browser crop
interactions were not verified. The browser automation attempts timed out before
navigation. The requirements now pin compatible OpenCV versions, but the existing
local environment was not reinstalled. The app remains a local, single-document,
single-worker editor; the cropper requires its external CDN.

</details>

## What it does

1. **Upload** a PDF (or a PNG/JPG) via `POST /uploadfiles/`.
   - A PDF is rendered page-by-page into images (`backend/engines/image_converter_engine.py`)
     and saved to `saved_pages/`.
   - A PNG/JPG is normalized into a saved page and opened in the same editor.
   - A successful upload replaces the previous document's working pages. Failed
     uploads leave the previous document intact.
2. **Crop & translate** a region of a page via `POST /cropimage/`:
   - The selected crop is OCR'd with PaddleOCR (`backend/engines/ocr_engine.py`).
   - The extracted English text is sent to Google's Gemini API
     (`backend/engines/translation_engine.py`) with a system prompt tuned for
     apparel/tech-pack/BOM terminology, translating it into Vietnamese factory-floor
     terminology.
   - The translated text is drawn back onto the image in place of the original
     (`backend/engines/image_manipulation_engine.py`).
3. **Compile** the edited pages back into a single PDF via `POST /compilepdf/`
   (`backend/engines/pdf_compiler_engine.py`), served back as a `FileResponse`.
4. **Clear** all working pages via `DELETE /deletefiles/`.

The frontend (`static/`) is a vanilla HTML/CSS/JS, Canva-style page editor: a page
strip along the bottom, a crop tool (`static/cropper/`), and a toolbar for
upload/compile/clear/toggle-selection-mode, calling the API via `static/utils/api.js`.

## Project layout

```
app.py                      FastAPI app & route definitions
backend/
  engines/                  OCR, translation, PDF<->image conversion, image editing
  common/                   shared Pydantic schemas/types (e.g. CropData)
  utils/                    path helpers
.env                        GEMINI_API_KEY (not committed; backend/.env also supported)
static/                     frontend (index.html, script.js, styles.css, cropper/, utils/)
saved_pages/                working directory of per-page PNGs generated from an upload
notes/                      dated dev-log notes explaining past changes
depracated/                 old/retired code kept for reference
output.pdf, image.png, testing.png   sample/working artifacts
```

## Running it

Use **64-bit Python 3.11**, the version used for this project's checks. The pinned
PaddleOCR/PaddlePaddle stack is older, so newer Python versions are not assumed
compatible. Run these commands from the project directory (Windows PowerShell):

```powershell
py -3.11 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pip check
```

The OpenCV pins align the direct and transitive packages with NumPy 1.26. If an
existing environment reports an incompatible `opencv-python-headless` version,
install the updated requirements before using OCR.

Add a project-root `.env` with:

```
GEMINI_API_KEY=your-key-here
```

Existing `backend/.env` files are also supported. Existing environment variables
take precedence, followed by the root `.env`, then `backend/.env` for values still
missing. Optional settings are `GEMINI_MODEL` (defaults to
`gemini-3.1-flash-lite`) and `TRANSFILER_FONT` (path to a TrueType font supporting
Vietnamese, if the system fonts are unsuitable).

Then run:

```powershell
.\venv\Scripts\python.exe -m uvicorn app:app --reload
```

Open `http://127.0.0.1:8000/`. The frontend is served at `/` (from `static/`), the API under the routes above, and
generated page images under `/saved_pages`.

OCR models and the translation client initialize when first needed. The first
OCR operation may need internet access to obtain PaddleOCR model files. Translation
requires a valid Gemini key and network access; uploading or compiling a document
does not make a translation API call.

This is a local editor with one shared working document in `saved_pages/`.
Separate browser tabs share those pages. Run one server worker and keep the server
bound to the loopback address for local use.

## Regression checks

From the project directory:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/frontend.test.mjs
```

The frontend checks need Node.js with its built-in test runner (Node 24 was used
locally). The Python checks use temporary documents and substitute OCR/translation services
where needed. They do not require paid API calls or change the user's working
pages. Passing these checks does not establish real OCR accuracy or translation
quality; those still need a sample document and a configured Gemini account.

## Roadmap

- Better visual guidance.
- Improved cropping systems.
- More accurate translation.

## Notes

- `notes/` contains dated write-ups of past changes and the reasoning behind them —
  useful background before modifying the frontend or the PDF/image pipeline.
- `depracated/translation_engine.py` is an older version of the translation engine,
  superseded by `backend/engines/translation_engine.py`.
