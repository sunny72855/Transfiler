# Transfiler

Current release: **Patch v0.1.1**.

A small FastAPI app for translating English garment-manufacturing PDFs/images into
Vietnamese, built around a scan → OCR → translate → re-draw → recompile workflow.

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
