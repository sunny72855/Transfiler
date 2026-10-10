import os, io
from PIL import Image, ImageDraw, ImageFont
from backend.common.common_schemas import CropData
from backend.common.common_types import Point
from backend.utils.path import safe_resolve_path

# Take in an image path and draw a rectangle and text over the given coordinates.
def edit_image(region: CropData, text: str) -> None:

    print("Test")
    print(region.imageDir)
    print("Finish test")

    imageDir = safe_resolve_path(region.imageDir)

    print(imageDir)

    if not os.path.exists(imageDir):
        return
    
    firstPoint = (region.x, region.y)
    secondPoint = (region.secondX, region.secondY)

    with Image.open(imageDir) as img:
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [firstPoint,
            secondPoint],
            fill="black"
        )

        font_size = get_font_size(
            draw,
            firstPoint,
            secondPoint,
            text
        )
        font = ImageFont.truetype("arial.ttf", font_size)

        draw.text(
            firstPoint,
            text,
            fill="white",
            font=font
        )

        img.save(imageDir, "PNG")

# Use binary search to find the optimal font size confined within a rectangle box
def get_font_size(draw: ImageDraw.ImageDraw, top_left: Point, bottom_right: Point, text: str) -> int:

    width = bottom_right[0] - top_left[0]
    height = bottom_right[1] - top_left[1]

    low = 1
    high = min(width, height)
    best = 1

    while low <= high:
        mid = (low + high) // 2

        font = ImageFont.truetype("arial.ttf", mid)

        bbox = draw.textbbox(
            (0, 0),
            text,
            font=font
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        if text_width <= width and text_height <= height:
            best = mid
            low = mid + 1
        else:
            high = mid - 1

    return best


# Getting cropped bytes for ocr engine
def crop_images(data: CropData) -> bytes:

    imageDir = safe_resolve_path(data.imageDir)

    with Image.open(imageDir) as img:

        (left, upper, right, lower) = (data.x, data.y, data.secondX, data.secondY)

        img_crop = img.crop((left, upper, right, lower))

    # 1. Create an in-memory bytes buffer
    crop_buffer = io.BytesIO()

    # 2. Save the cropped image into the buffer as a formatted PNG
    # (We pass img.format to keep the original file type, defaulting to PNG if it's missing)
    img_crop.save(crop_buffer, format=img.format or 'PNG')

    # 3. Extract the actual formatted file bytes
    img_bytes = crop_buffer.getvalue()

    return img_bytes