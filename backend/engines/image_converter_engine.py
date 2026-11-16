"""Prepare a complete new document before replacing the working pages."""

import io
import os
import shutil
import tempfile
from pathlib import Path

import fitz
from PIL import Image, ImageOps, UnidentifiedImageError

from backend.utils.pages import saved_page_paths


def _publish_pages(staging: Path, output_dir: Path) -> list[str]:
    """Roll back on a failed replacement instead of leaving a mixed document."""
    output_dir.mkdir(parents=True, exist_ok=True)
    new_pages = saved_page_paths(staging)
    if not new_pages:
        raise ValueError("The uploaded document contains no pages.")
    backup = Path(tempfile.mkdtemp(prefix=".transfiler-backup-", dir=output_dir.parent))
    moved_old = []
    moved_new = []
    keep_backup = False
    try:
        try:
            for old in saved_page_paths(output_dir):
                destination = backup / old.name
                os.replace(old, destination)
                moved_old.append(destination)
            for page in new_pages:
                destination = output_dir / page.name
                os.replace(page, destination)
                moved_new.append(destination)
        except Exception as original_error:
            recovery_errors = []
            for page in moved_new:
                try:
                    page.unlink(missing_ok=True)
                except OSError as error:
                    recovery_errors.append(error)
            for old in moved_old:
                try:
                    os.replace(old, output_dir / old.name)
                except OSError as error:
                    recovery_errors.append(error)
            if recovery_errors:
                # Disk/permission failures may also prevent rollback. Preserve
                # the recovery files instead of auto-deleting the only originals.
                keep_backup = True
                raise RuntimeError(f"Document rollback failed. Recovery pages are preserved in {backup}.") from original_error
            raise
    finally:
        if not keep_backup:
            # Only remove the private temporary directory created above.
            if backup.parent.resolve() != output_dir.parent.resolve() or not backup.name.startswith(".transfiler-backup-"):
                raise RuntimeError("Unexpected backup directory; refusing cleanup.")
            shutil.rmtree(backup)
    return [page.name for page in new_pages]


def convert_pdf_to_images(file_content: bytes, output_dir: str) -> list[str]:
    output = Path(output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".transfiler-upload-", dir=output.parent) as temporary:
        staging = Path(temporary)
        try:
            with fitz.open(stream=file_content, filetype="pdf") as doc:
                if doc.needs_pass:
                    raise ValueError("Password-protected PDFs are not supported.")
                if not len(doc):
                    raise ValueError("The uploaded PDF contains no pages.")
                for number, page in enumerate(doc, start=1):
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csRGB)
                    pix.save(staging / f"page_{number}.png")
        except (fitz.FileDataError, fitz.EmptyFileError) as error:
            raise ValueError("The uploaded PDF is empty or damaged.") from error
        return _publish_pages(staging, output)


def convert_image_to_pages(file_content: bytes, output_dir: str) -> list[str]:
    """Normalize JPEG/PNG uploads to the same PNG-page contract as PDFs."""
    output = Path(output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".transfiler-upload-", dir=output.parent) as temporary:
        staging = Path(temporary)
        try:
            with Image.open(io.BytesIO(file_content)) as source:
                if source.format not in {"PNG", "JPEG"}:
                    raise ValueError("Please upload a PDF, PNG, or JPG.")
                oriented = ImageOps.exif_transpose(source)
                rgba = oriented.convert("RGBA")
                with Image.new("RGB", rgba.size, "white") as page:
                    page.paste(rgba, mask=rgba.getchannel("A"))
                    page.save(staging / "page_1.png", format="PNG")
                rgba.close()
                if oriented is not source:
                    oriented.close()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise ValueError("The uploaded image is damaged or too large to decode.") from error
        return _publish_pages(staging, output)
