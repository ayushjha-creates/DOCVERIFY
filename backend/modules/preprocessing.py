import os
import fitz
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np
import cv2
import tempfile

def convert_pdf_to_images(pdf_path, output_dir, dpi=200):
    images = []
    doc = fitz.open(pdf_path)
    for page_num in range(len(doc)):
        pix = doc[page_num].get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
        img_data = pix.tobytes("png")
        page_path = os.path.join(output_dir, f"page_{page_num}.png")
        with open(page_path, "wb") as f:
            f.write(img_data)
        images.append(page_path)
    doc.close()
    return images

def clean_image(image_path):
    img = cv2.imread(image_path)
    if img is None:
        img_pil = Image.open(image_path).convert("RGB")
        img = np.array(img_pil)
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)
    cleaned_path = image_path.replace(".png", "_cleaned.png")
    cv2.imwrite(cleaned_path, enhanced)
    return cleaned_path

def get_image_preview(image_path, max_width=400):
    img = Image.open(image_path)
    img.thumbnail((max_width, max_width * img.height // img.width))
    preview_path = image_path.replace(".png", "_preview.png")
    img.save(preview_path)
    return preview_path

def preprocess_document(file_path, output_dir=None):
    ext = os.path.splitext(file_path)[1].lower()
    images = []
    if output_dir is None:
        output_dir = os.path.dirname(file_path)
    os.makedirs(output_dir, exist_ok=True)

    if ext in ['.pdf']:
        images = convert_pdf_to_images(file_path, output_dir)
    elif ext in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
        img_path = os.path.join(output_dir, f"page_0.png")
        img = Image.open(file_path)
        img.save(img_path)
        images = [img_path]

    cleaned_images = []
    for img_path in images:
        cleaned = clean_image(img_path)
        cleaned_images.append(cleaned)
    return images, cleaned_images
