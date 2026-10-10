from pathlib import Path
from PIL import Image

# Image.open() only registers the plugin for the format it opens (PNG here).
# The PDF saver embeds pages as JPEG internally, so the JPEG encoder must be
# registered too - Image.init() loads every plugin up front to guarantee that.
Image.init()


def compile_images_to_pdf(input_dir: str = "saved_pages", output_pdf: str = "output.pdf") -> str:
    input_path = Path(input_dir)
    output_path = Path(output_pdf)

    # Sort numerically on the page number instead of the filename string,
    # otherwise "page_10.png" sorts before "page_2.png".
    paths = sorted(
        input_path.glob("*.png"),
        key=lambda p: int(p.stem.split("_")[1])
    )

    images = [
        Image.open(path).convert("RGB")
        for path in paths
    ]

    if images:
        images[0].save(
            output_path,
            save_all=True,
            append_images=images[1:]
        )

    for image in images:
        image.close()

    return str(output_path)