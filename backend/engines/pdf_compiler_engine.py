import os
import tempfile
from pathlib import Path

from PIL import Image

from backend.utils.pages import saved_page_paths

# Register the JPEG encoder used by Pillow's PDF writer as well as PNG readers.
Image.init()


class NoImagesError(ValueError):
    """Raised when there are no saved page images to compile."""


def has_saved_images(input_dir: str = "saved_pages") -> bool:
    return bool(saved_page_paths(input_dir))


def compile_images_to_pdf(input_dir: str = "saved_pages", output_pdf: str = "output.pdf") -> str:
    paths = saved_page_paths(input_dir)
    if not paths:
        raise NoImagesError("No files have been uploaded. Please upload a file before compiling.")

    output_path = Path(output_pdf)
    images = []
    temporary_path = None
    try:
        for path in paths:
            with Image.open(path) as source:
                images.append(source.convert("RGB"))
        # Write beside the output for an atomic replacement on the same filesystem.
        with tempfile.NamedTemporaryFile(suffix=".pdf", prefix=".transfiler-", dir=output_path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
        images[0].save(temporary_path, format="PDF", save_all=True, append_images=images[1:])
        os.replace(temporary_path, output_path)
    finally:
        for image in images:
            image.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return str(output_path)
