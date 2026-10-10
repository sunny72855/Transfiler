from paddleocr import PaddleOCR
import numpy as np
import cv2

ocr = PaddleOCR(lang="en")

def run_ocr_on_bytes(file_bytes: bytes) -> str:
    # Turn raw uploaded network bytes into a real image matrix for OpenCV
    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # Run OCR
    # result is a list of pages, so we take result[0]
    result = ocr.ocr(img, cls=True)[0]
    
    extracted_text = ""

    # Since result is now a flat list of lines, we can loop directly
    for line in result:
        # line is [ [box], (text, confidence) ]
        # We access the tuple at index 1, then the string at index 0
        text = line[1][0]
        extracted_text += text + "\n"

    return extracted_text