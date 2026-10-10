import os
import fitz  # This is PyMuPDF

# Define the folder name where we will store the generated page images
OUTPUT_DIR = "saved_pages"

# Create the folder automatically if it doesn't exist yet
os.makedirs(OUTPUT_DIR, exist_ok=True)

def convert_pdf_to_images(file_content: bytes, output_dir: str) -> list:
    # Open the PDF directly out of the raw memory bytes
    doc = fitz.open(stream=file_content, filetype="pdf")

    # Defining a list containing directory of each of the images
    saved_images = []

    for page_number in range(len(doc)):
        
        # 0. Define the matrix
        zoom_matrix = fitz.Matrix(2.0, 2.0)
        
        # 1. Load the specific page based on the current loop number
        page = doc.load_page(page_number)
        
        # 2. Render that page into a pixel map (image data in RAM)
        pix = page.get_pixmap(matrix=zoom_matrix)

        # 3. Create a unique filename for this page (e.g., "page_1.png")
        image_filename = f"page_{page_number + 1}.png"
        
        # 4. Combine it with your target folder (e.g., "saved_pages/page_1.png")
        image_path = os.path.join(output_dir, image_filename)
        
        # 5. Write the pixels to disk
        pix.save(image_path)

        saved_images.append(image_filename)

    # 6. Prevent memory leaking
    doc.close()

    return saved_images