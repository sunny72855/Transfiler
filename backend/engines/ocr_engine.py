from threading import Lock


_ocr = None
_initialization_lock = Lock()
_inference_lock = Lock()


def _get_ocr():
    global _ocr
    if _ocr is None:
        with _initialization_lock:
            if _ocr is None:
                try:
                    from paddleocr import PaddleOCR
                    _ocr = PaddleOCR(lang="en", use_angle_cls=True, use_gpu=False, show_log=False)
                except Exception as error:
                    raise RuntimeError("OCR could not be initialized. Check the PaddleOCR installation and model files.") from error
    return _ocr


def run_ocr_on_bytes(file_bytes: bytes) -> str:
    if not file_bytes:
        raise ValueError("The image is empty.")
    try:
        import cv2
        import numpy as np
    except ImportError as error:
        raise RuntimeError("OCR image dependencies are unavailable.") from error
    encoded = np.frombuffer(file_bytes, np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The uploaded image could not be decoded.")
    try:
        # A Paddle predictor is shared between requests and is not thread-safe.
        with _inference_lock:
            result = _get_ocr().ocr(image, cls=True)
        if not result or not result[0]:
            return ""
        return "\n".join(line[1][0] for line in result[0])
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError("OCR could not read the selected image.") from error
