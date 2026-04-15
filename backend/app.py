import os
import json
import time
import base64
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sock import Sock
from dotenv import load_dotenv
from groq import Groq

import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

from utils.image import compress_image, base64_to_image, preprocess_for_ocr
from utils.cache import cache
from voice.intent import parse_intent, get_help_text

load_dotenv()

app = Flask(__name__)
CORS(app)
sock = Sock(app)


_yolo_model = None

def get_yolo():
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        _yolo_model = YOLO('yolo11x.pt')
    return _yolo_model

def has_internet():
    """Check if internet is available"""
    import socket
    try:
        socket.setdefaulttimeout(3)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except Exception:
        return False

def call_steve(image_b64, prompt, max_tokens=300):
    client = Groq(api_key=os.getenv('GROQ_API_KEY'))
    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ],
        max_tokens=max_tokens,
        temperature=0.3
    )
    return response.choices[0].message.content

def run_yolo(img_np):
    model = get_yolo()
    results = model(img_np, verbose=False)
    detections = []

    for result in results:
        for box in result.boxes[:10]:
            cls_id = int(box.cls[0])
            confidence = float(box.conf[0])
            label = result.names[cls_id]

            if confidence < 0.3:
                continue

            # Position (left/center/right)
            x_center = float(box.xywh[0][0])
            img_width = img_np.shape[1]
            if x_center < img_width / 3:
                position = "to your left"
            elif x_center > 2 * img_width / 3:
                position = "to your right"
            else:
                position = "in front of you"

            # Distance based on box size ratio
            box_area = float(box.xywh[0][2] * box.xywh[0][3])
            img_area = img_np.shape[0] * img_np.shape[1]
            ratio = box_area / img_area
            if ratio > 0.25:
                distance = "very close"
            elif ratio > 0.08:
                distance = "nearby"
            elif ratio > 0.03:
                distance = "a few meters away"
            else:
                distance = "far away"

            detections.append(f"{label} {position} {distance}")

    if detections:
        count = len(detections)
        return f"I can see {count} object{'s' if count > 1 else ''}: " + ", ".join(detections[:10])
    return "No objects detected in the scene"

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "ai": "groq-llama4-scout",
        "ocr": "tesseract",
        "detection": "yolo11x",
        "timestamp": time.time(),
        "cache_size": cache.size()
    })

"""@app.route('/describe', methods=['POST'])
def describe():
    data = request.json
    image_b64 = compress_image(data['image'])
    cache_key = cache.make_key(image_b64, 'describe')

    cached = cache.get(cache_key)
    if cached:
        return jsonify({"result": cached, "cached": True})

    prompt = (
        "You are an assistant for a blind person. "
        "In 2 short sentences: first describe what is directly ahead, "
        "then warn about any immediate obstacles or hazards. "
        "Be specific about distances: say 'very close' under 1 meter, "
        "'nearby' for 1-3 meters, 'ahead' for further. "
        "Use simple clear language."
    )
    result = call_steve(image_b64, prompt)
    cache.set(cache_key, result)
    return jsonify({"result": result, "cached": False})"""

@app.route('/describe', methods=['POST'])
def describe():
    data = request.json
    image_b64 = compress_image(data['image'])
    cache_key = cache.make_key(image_b64, 'describe')

    cached = cache.get(cache_key)
    if cached:
        return jsonify({"result": cached, "cached": True})

    # Step 1 — Run YOLO first (fast, offline)
    image = base64_to_image(image_b64)
    img_np = np.array(image)
    model = get_yolo()
    yolo_results = model(img_np, verbose=False)

    detections = []
    for result in yolo_results:
        for box in result.boxes[:10]:
            cls_id = int(box.cls[0])
            confidence = float(box.conf[0])
            label = result.names[cls_id]

            if confidence < 0.3:
                continue

            x_center = float(box.xywh[0][0])
            img_width = img_np.shape[1]
            if x_center < img_width / 3:
                position = "to your left"
            elif x_center > 2 * img_width / 3:
                position = "to your right"
            else:
                position = "in front of you"

            box_area = float(box.xywh[0][2] * box.xywh[0][3])
            img_area = img_np.shape[0] * img_np.shape[1]
            ratio = box_area / img_area
            if ratio > 0.25:
                distance = "very close"
            elif ratio > 0.08:
                distance = "nearby"
            elif ratio > 0.03:
                distance = "a few meters away"
            else:
                distance = "far away"

            detections.append(f"{label} {position} {distance}")

    # Step 2 — Send YOLO results + image to Groq
    if detections:
        yolo_context = ", ".join(detections[:10])
        prompt = (
            f"You are an assistant for a blind person. "
            f"YOLO object detection found: {yolo_context}. "
            f"Using this information and the image, give a clear natural "
            f"2 sentence description of what's ahead. "
            f"Mention the most important objects and any dangers. "
            f"Be specific about distances and directions. "
            f"Use simple clear language."
        )
    else:
        prompt = (
            "You are an assistant for a blind person. "
            "In 2 short sentences describe what is directly ahead "
            "and warn about any obstacles. "
            "Be specific about distances. Use simple clear language."
        )

    result = call_steve(image_b64, prompt)
    cache.set(cache_key, result)
    return jsonify({"result": result, "cached": False})


@app.route('/find', methods=['POST'])
def find():
    data = request.json
    image_b64 = compress_image(data['image'])
    object_name = data.get('object', 'object')
    cache_key = cache.make_key(image_b64, f'find_{object_name}')

    cached = cache.get(cache_key)
    if cached:
        return jsonify({"result": cached, "cached": True})

    prompt = (
        f"Is there a {object_name} visible in this image? "
        "If yes, say exactly where: left side, right side, center, "
        "near, or far. If no, say it is not visible. "
        "Maximum 1 sentence. Be direct."
    )
    result = call_steve(image_b64, prompt, max_tokens=100)
    cache.set(cache_key, result)
    return jsonify({"result": result, "cached": False})


"""@app.route('/read', methods=['POST'])
def read_text():
    data = request.json
    image_b64 = compress_image(data['image'])
    cache_key = cache.make_key(image_b64, 'read')

    cached = cache.get(cache_key)
    if cached:
        return jsonify({"result": cached, "cached": True})

    # Try Tesseract first
    image = base64_to_image(image_b64)
    processed = preprocess_for_ocr(image)
    text = pytesseract.image_to_string(
        processed,
        config='--psm 6 --oem 3 -l eng --dpi 300'
    ).strip()

    # Clean up
    text = ' '.join(text.split())
    words = [w for w in text.split() if len(w) > 1]

    if len(words) >= 2:
        # Tesseract worked
        result = text
    else:
        # Fall back to Groq
        prompt = (
            "You are an OCR assistant for a blind person. "
            "Read ALL text visible in this image exactly as written. "
            "Output ONLY the text. If no text say 'No text found'."
        )
        result = call_steve(image_b64, prompt, max_tokens=200)

    cache.set(cache_key, result)
    return jsonify({"result": result, "cached": False})"""

@app.route('/read', methods=['POST'])
def read_text():
    data = request.json
    image_b64 = compress_image(data['image'])
    cache_key = cache.make_key(image_b64, 'read')

    cached = cache.get(cache_key)
    if cached:
        return jsonify({"result": cached, "cached": True})

    prompt = (
        "You are an OCR assistant for a blind person. "
        "Carefully read ALL text visible in this image. "
        "Include signs, labels, books, screens, anything with text. "
        "Output ONLY the text you see, word by word. "
        "If no text is visible say 'No text found'."
    )
    result = call_steve(image_b64, prompt, max_tokens=200)

    cache.set(cache_key, result)
    return jsonify({"result": result, "cached": False})


@app.route('/navigate', methods=['POST'])
def navigate():
    data = request.json
    image_b64 = compress_image(data['image'])
    cache_key = cache.make_key(image_b64, 'navigate')

    cached = cache.get(cache_key)
    if cached:
        return jsonify({"result": cached, "cached": True})

    prompt = (
        "You are a navigation assistant for a blind person. "
        "Is the path ahead clear to walk? "
        "Are there any obstacles? If yes, where and how close? "
        "What surface is ahead? "
        "Be concise, max 2 sentences. Start with CLEAR or WARNING."
    )
    result = call_steve(image_b64, prompt, max_tokens=150)
    cache.set(cache_key, result)
    return jsonify({"result": result, "cached": False})


@app.route('/detect', methods=['POST'])
def detect():
    data = request.json
    image_b64 = compress_image(data['image'])
    cache_key = cache.make_key(image_b64, 'detect')

    cached = cache.get(cache_key)
    if cached:
        return jsonify({"result": cached, "cached": True})

    image = base64_to_image(image_b64)
    img_np = np.array(image)
    result = run_yolo(img_np)

    cache.set(cache_key, result)
    return jsonify({"result": result, "cached": False})


@app.route('/command', methods=['POST'])
def command():
    data = request.json
    text = data.get('text', '')
    intent = parse_intent(text)

    if intent['intent'] == 'help':
        return jsonify({"result": get_help_text(), "intent": "help"})
    if intent['intent'] == 'stop':
        return jsonify({"result": "Stopped.", "intent": "stop"})
    if intent['intent'] == 'unknown':
        return jsonify({
            "result": "Command not understood. Say help to hear available commands.",
            "intent": "unknown"
        })

    if not data.get('image'):
        return jsonify({"error": "Image required"}), 400

    if intent['intent'] == 'describe':
        return describe()
    elif intent['intent'] == 'read':
        return read_text()
    elif intent['intent'] == 'navigate':
        return navigate()
    elif intent['intent'] == 'find':
        request.json['object'] = intent.get('object', 'object')
        return find()


@sock.route('/ws')
def websocket(ws):
    print("📱 Client connected via WebSocket")
    while True:
        try:
            raw = ws.receive()
            if not raw:
                break

            data = json.loads(raw)
            action = data.get('action', 'describe')
            image_b64 = data.get('image', '')

            if not image_b64:
                ws.send(json.dumps({"error": "No image provided"}))
                continue

            ws.send(json.dumps({"status": "processing", "action": action}))

            image_b64 = compress_image(image_b64)
            cache_key = cache.make_key(image_b64, action)
            cached = cache.get(cache_key)

            if cached:
                result = cached
            elif action == 'describe':
                result = call_steve(image_b64,
                    "You are an assistant for a blind person. "
                    "In 2 short sentences describe what's ahead and warn about obstacles. "
                    "Mention distances: very close, nearby, or ahead.")
            elif action == 'read':
                image = base64_to_image(image_b64)
                processed = preprocess_for_ocr(image)
                result = pytesseract.image_to_string(
                    processed,
                    config='--psm 6 --oem 3'
                ).strip() or "No text found"
            elif action == 'find':
                obj = data.get('object', 'object')
                result = call_steve(image_b64,
                    f"Is there a {obj} visible? If yes, where exactly. "
                    "If no, say not visible. One sentence only.")
            elif action == 'navigate':
                result = call_steve(image_b64,
                    "Is the path ahead clear to walk? Any obstacles? "
                    "Start with CLEAR or WARNING. Max 2 sentences.")
            elif action == 'detect':
                image = base64_to_image(image_b64)
                img_np = np.array(image)
                result = run_yolo(img_np)
            else:
                result = "Unknown action"

            cache.set(cache_key, result)
            ws.send(json.dumps({
                "result": result,
                "action": action,
                "timestamp": time.time()
            }))

        except Exception as e:
            print(f"WebSocket error: {e}")
            try:
                ws.send(json.dumps({"error": str(e)}))
            except:
                break

    print(" Client disconnected")

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'True') == 'True'
    print(f"VisionAid backend running on port {port}")
    print(f"AI: Groq Llama4 Scout (Free)")
    print(f" OCR: Tesseract (Offline)")
    print(f" Detection: YOLO11x (Offline)")
    print(f"WebSocket available at ws://localhost:{port}/ws")
    app.run(host='0.0.0.0', port=port, debug=debug)