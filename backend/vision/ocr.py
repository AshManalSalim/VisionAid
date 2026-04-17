import pytesseract
import numpy as np

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def read_with_tesseract(processed_image):
    """Read text using Tesseract OCR"""
    text = pytesseract.image_to_string(
        processed_image,
        config='--psm 6 --oem 3 -l eng --dpi 300'
    ).strip()
    text = ' '.join(text.split())
    return text


def build_ocr_prompt():
    """Build Groq prompt for OCR"""
    return (
        "You are an OCR assistant for a blind person. "
        "Carefully read ALL text visible in this image. "
        "Include signs, labels, books, screens, anything with text. "
        "Output ONLY the text you see, word by word. "
        "If no text is visible say 'No text found'."
    )


def read_text(image_b64, processed_image, call_ai, has_internet):
    """
    Read text from image.
    Uses Groq online for best accuracy, Tesseract offline as fallback.
    """
    if not has_internet:
        text = read_with_tesseract(processed_image)
        return text if text else "No text detected. Internet required for better reading."

    # Online → Groq Vision
    prompt = build_ocr_prompt()
    return call_ai(image_b64, prompt, max_tokens=200)