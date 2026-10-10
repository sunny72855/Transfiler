# Transfiler

A small FastAPI app for translating English garment-manufacturing PDFs/images into
Vietnamese, built around a scan → OCR → translate → re-draw → recompile workflow.

## What it does

1. **Upload** a PDF (or a PNG/JPG) via `POST /uploadfiles/`.
   - A PDF is rendered page-by-page into images (`backend/engines/image_converter_engine.py`)
     and saved to `saved_pages/`.
   - A PNG/JPG is run straight through OCR.
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
  .env                      GEMINI_API_KEY (not committed)
static/                     frontend (index.html, script.js, styles.css, cropper/, utils/)
saved_pages/                working directory of per-page PNGs generated from an upload
notes/                      dated dev-log notes explaining past changes
depracated/                 old/retired code kept for reference
output.pdf, image.png, testing.png   sample/working artifacts
```

## Running it

```bash
pip install -r requirements.txt   # fastapi, uvicorn, paddleocr, opencv-python, google-genai, python-dotenv, python-multipart
```

Add a `backend/.env` with:

```
GEMINI_API_KEY=your-key-here
```

Then run:

```bash
uvicorn app:app --reload
```

The frontend is served at `/` (from `static/`), the API under the routes above, and
generated page images under `/images`.

## Notes

- `notes/` contains dated write-ups of past changes and the reasoning behind them —
  useful background before modifying the frontend or the PDF/image pipeline.
- `depracated/translation_engine.py` is an older version of the translation engine,
  superseded by `backend/engines/translation_engine.py`.
