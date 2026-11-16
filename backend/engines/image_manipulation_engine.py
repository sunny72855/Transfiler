import io
import math
import os
import tempfile
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from backend.common.common_schemas import CropData
from backend.common.common_types import Point
from backend.utils.path import safe_resolve_path


@lru_cache(maxsize=128)
def _load_font(size: int, configured_font: str = ""):
    candidates = [configured_font] if configured_font else [
        "arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    raise RuntimeError(
        "A Unicode TrueType font is required. Install Arial/DejaVu Sans or set TRANSFILER_FONT."
    )


def _font(size: int):
    return _load_font(size, os.getenv("TRANSFILER_FONT", ""))


def _crop_box(data: CropData, image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = image_size
    values = (data.x, data.y, data.secondX, data.secondY)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Crop coordinates must be finite.")
    if data.x < 0 or data.y < 0 or data.secondX <= data.x or data.secondY <= data.y:
        raise ValueError("Select a rectangle with positive width and height.")
    if data.x >= width or data.y >= height or data.secondX > width + 1e-6 or data.secondY > height + 1e-6:
        raise ValueError("The selected rectangle extends outside the image.")
    # Use the same integer pixel bounds for OCR and replacement, including fractional edges.
    return (math.floor(data.x), math.floor(data.y),
            min(width, math.ceil(data.secondX)), min(height, math.ceil(data.secondY)))


def get_font_size(draw: ImageDraw.ImageDraw, top_left: Point, bottom_right: Point, text: str) -> int:
    """Find the largest measured multiline font that fits entirely inside the box."""
    width = bottom_right[0] - top_left[0]
    height = bottom_right[1] - top_left[1]
    if width <= 0 or height <= 0 or not text or not text.strip():
        raise ValueError("A positive rectangle and nonempty text are required.")
    low, high, best = 1, max(1, math.ceil(max(width, height) * 2)), 0
    while low <= high:
        mid = (low + high) // 2
        bbox = draw.multiline_textbbox((0, 0), text, font=_font(mid), spacing=0)
        if bbox[2] - bbox[0] <= width and bbox[3] - bbox[1] <= height:
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    if not best:
        raise ValueError("The translated text cannot fit inside this selection. Select a larger area.")
    return best


def edit_image(region: CropData, text: str) -> None:
    """Replace only the selected pixels, committing the edited image atomically."""
    if not text or not text.strip():
        raise ValueError("Translation returned no text; the image was not changed.")
    image_path = safe_resolve_path(region.imageDir)
    with Image.open(image_path) as original:
        box = _crop_box(region, original.size)
        img = original.convert("RGBA" if original.mode == "RGBA" else "RGB")
    with img:
        left, top, right, bottom = box
        draw = ImageDraw.Draw(img)
        font = _font(get_font_size(draw, (left, top), (right, bottom), text))
        bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=0)
        # Pillow's rectangle endpoint is inclusive; crop() uses an exclusive endpoint.
        draw.rectangle((left, top, right - 1, bottom - 1), fill="black")
        # Glyph bearings can be negative and accents add a top offset. Compensate
        # for the measured bounds so all drawn pixels stay inside the selection.
        draw.multiline_text((left - bbox[0], top - bbox[1]), text,
                            fill="white", font=font, spacing=0)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".crop-", suffix=".png", dir=image_path.parent)
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            img.save(temporary_path, "PNG")
            os.replace(temporary_path, image_path)
        finally:
            temporary_path.unlink(missing_ok=True)


def crop_images(data: CropData) -> bytes:
    image_path = safe_resolve_path(data.imageDir)
    with Image.open(image_path) as img:
        box = _crop_box(data, img.size)
        with img.crop(box) as cropped, io.BytesIO() as buffer:
            cropped.save(buffer, format="PNG")
            return buffer.getvalue()
