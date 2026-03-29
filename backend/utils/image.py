import base64
import io
import cv2
import numpy as np 
from PIL import Image, ImageEnhance


def base64_to_image(b64_string):
    image_data= base64.b64decode(b64_string)
    image = Image.open(io.BytesIO(image_data))
    return image

def image_to_base64(image):
    buffer= io.BytesIO()
    image.save(buffer, format='JPEG',quality=85)
    return base64.b64encode(buffer.getvalue()).decode('utf-8')
def image_to_numpy(image):
    return np.array(image)
def preprocess_for_ocr(image):
    img_np = np.array(image)
    gray= cv2.cvtColor(img_np,cv2.COLOR_RGB2GRAY)
    clahe= cv2.createCLAHE(clipLimit=2.0 ,tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    denoised = cv2.fastNlMeansDenoising(enhanced, h=10)
    return Image.fromarray(denoised)
def preprocess_for_vision(image, max_size=1024):
    width, height =image.size
    if max(width, height) > max_size:
        ratio = max_size/ max(width,height)
        new_size=(int(width*ratio),int(height*ratio))
        image= image.resize(new_size,Image.LANCZOS)
    enhancer= ImageEnhance.Brightness(image)
    image= enhancer.enhance(1.1)
    return image
def compress_image(b64_string, quality=60):
    image= base64_to_image(b64_string)
    image= preprocess_for_vision(image)
    if image.mode !='RGB':
        image= image.convert('RGB')
    return image_to_base64(image)      
