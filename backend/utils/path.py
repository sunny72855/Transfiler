from pathlib import Path
from urllib.parse import unquote, urlsplit
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAVED_PAGES_DIR = PROJECT_ROOT / "saved_pages"


def safe_resolve_path(incoming_path: str) -> Path:
    """Resolve a public page URL, permitting only PNGs in the working folder."""
    if not isinstance(incoming_path, str) or not incoming_path.strip():
        raise ValueError("An image path is required.")
    try:
        parsed = urlsplit(incoming_path)
    except ValueError as error:
        raise ValueError("Invalid image URL.") from error
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Unsupported image URL.")
    path = unquote(parsed.path)
    # Backslashes are path separators on Windows, and must not bypass this check.
    if "\\" in path or "\x00" in path:
        raise ValueError("Invalid image path.")
    parts = path.lstrip("/").split("/")
    if len(parts) != 2 or parts[0] != "saved_pages" or parts[1] in {"", ".", ".."}:
        raise ValueError("Select an image from saved_pages.")
    if re.fullmatch(r"page_[1-9]\d*\.png", parts[1]) is None:
        raise ValueError("Select a saved page PNG image.")
    root = SAVED_PAGES_DIR.resolve()
    candidate = (root / parts[1]).resolve()
    # resolve() follows symlinks as well as '..'; containment is checked afterwards.
    if candidate.parent != root or candidate.suffix.lower() != ".png":
        raise ValueError("Only saved page PNG images may be edited.")
    return candidate
