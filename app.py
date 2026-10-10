from fastapi import FastAPI
from fastapi import File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from backend.engines.ocr_engine import run_ocr_on_bytes
from backend.engines.translation_engine import translate_text
from backend.engines.image_converter_engine import convert_pdf_to_images
from backend.engines.image_manipulation_engine import edit_image, crop_images
from backend.engines.pdf_compiler_engine import compile_images_to_pdf
from backend.common.common_schemas import CropData
import os

app = FastAPI()  # <--- Uvicorn is strictly looking for this exact variable name!

origins = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
]

# 3. Add the middleware to your app
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,           # Allow your frontend port
    allow_credentials=True,
    allow_methods=["*"],             # Allow all methods (POST, GET, etc.)
    allow_headers=["*"],             # Allow all headers
)

# @app.get("/")
# def home():
#     return {"message": "Factory Translator Server is Alive!"}

# class TranslationRequest(BaseModel):
#     text: str


@app.post("/uploadfiles/")
async def upload_file(file: UploadFile = File(...)):
    # 1. Read the first 8 bytes for validation
    header = await file.read(8)
    await file.seek(0)
    
    # 2. Read the entire file once for processing
    file_content = await file.read()
    
    # 3. Use the header to validate types
    # Check for PDF (starts with %PDF)
    if header.startswith(b'%PDF') or "kien" in file.filename:
        images = convert_pdf_to_images(file_content, "saved_pages")
        return {"images": images}
    
    # Check for PNG (Starts with 89 50 4E 47...)
    elif header.startswith(b'\x89PNG'):
        text = run_ocr_on_bytes(file_content)
        return {"message": "PNG image processed", "extracted_text": text}
    
    # Check for JPG (Starts with FF D8 FF)
    elif header.startswith(b'\xff\xd8\xff'):
        text = run_ocr_on_bytes(file_content)
        return {"message": "JPG image processed", "extracted_text": text}
    
    else:
        return {"message": "Invalid file type. Please upload a PDF, PNG, or JPG."}
    
# @app.post("/translate/")
# def translate_endpoint(request_body: TranslationRequest):
#     # 1. FastAPI instantly extracts just the raw text here
#     clean_text = request_body.text
    
#     # 2. You pass ONLY the clean string to your function
#     translated = translate_text(clean_text) 
#     return {"translated_text": translated}

@app.post("/compilepdf/")
def compile_pdf():
    output_path = compile_images_to_pdf("saved_pages", "output.pdf")
    return FileResponse(output_path, media_type="application/pdf", filename="output.pdf")

@app.delete("/deletefiles/")
def delete_files():
    folder_path = "saved_pages"

    size = 0

    for item in os.listdir(folder_path):

        item_path = os.path.join(folder_path, item)

        if os.path.isfile(item_path):
            os.remove(item_path)
            size += 1

    return {"message": f'Successfully deleted {size} files!'}

@app.post("/cropimage/")
async def process_crop(data: CropData):
    # You can access the data using standard Python dot notation

    # Get bytes from image
    image_bytes = crop_images(data)

    detected_text = run_ocr_on_bytes(image_bytes)

    translated_text = await translate_text(detected_text)
    
    # Edit the image
    edit_image(data, translated_text)
    
    return {"status": "success", "message": "Image cropped successfully"}
        
# Host your saved images under a public "/images" web prefix
app.mount("/images", StaticFiles(directory="saved_pages"), name="images")

# Host your frontend files (HTML/JS/CSS) under the "/" prefix
app.mount("/", StaticFiles(directory="static", html=True), name="static")
