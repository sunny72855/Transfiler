from pathlib import Path
from urllib.parse import urlparse

# This resolves to the absolute path of the directory containing this file.
# Since paths.py is inside /utils, we use .parent.parent to go back to the root backend dir.
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

def safe_resolve_path(incoming_path: str) -> Path:
    """
    Cleans up an incoming path (handles full URLs, query parameters, leading slashes)
    and resolves it to an absolute system path relative to the backend root.
    """
    # 1. If the frontend sent a full URL (http://...), extract just the path portion
    if incoming_path.startswith("http"):
        incoming_path = urlparse(incoming_path).path
        
    # 2. Strip off any query parameters (like ?t=171000000)
    clean_path = incoming_path.split('?')[0]
    
    # 3. Strip leading slashes so Python treats it as a relative path
    clean_path = clean_path.lstrip('/')
    
    # 4. Join with the backend root directory
    return BACKEND_ROOT / clean_path