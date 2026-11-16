"""The working document consists only of numbered page_N.png files."""

import re
from pathlib import Path


def saved_page_paths(directory: str | Path) -> list[Path]:
    pages = []
    for path in Path(directory).glob("page_*.png"):
        match = re.fullmatch(r"page_([1-9]\d*)\.png", path.name)
        if match and path.is_file() and not path.is_symlink():
            pages.append((int(match.group(1)), path))
    return [path for _, path in sorted(pages)]
