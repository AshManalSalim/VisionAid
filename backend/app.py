import os
import json
import time
import base64
import socket
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sock import Sock
from dotenv import load_dotenv
from groq import Groq
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

from utils.image import compress_image, base64_to_image, preprocess_for_ocr
from utils.cache import cache
from voice.intent import parse_intent, get_help_text
from vision.detector import detect_objects, format_detections, has_danger
from vision.scene import describe_scene, navigate_scene
from vision.ocr import read_text
from vision.finder import find_object

load_dotenv()

app = Flask(__name__)
CORS(app)
sock = Sock(app)


# ── Internet check ────────────────────────────────────────────
def has_internet():
    try:
        socket.setdefaulttimeout(3)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except Exception:
        return False


# ── Groq AI ───────────────────────────────────────────────────
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
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
                    },
                    {"type": "text", "text": prompt}
                ]
            }
        ],
        max_tokens=max_tokens,
        temperature=0.3
    )
    return response.choices[0].message.content


# ── Health ────────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "ai": "groq-llama4-scout",
        "ocr": "tesseract + groq",
        "detection": "yolo11x",
        "timestamp": time.time(),
        "cache_size": cache.size()
    })


# ── Status ────────────────────────────────────────────────────
@app.route('/status', methods=['GET'])
def status():
    online = has_internet()
    return jsonify({
        "online": online,
        "mode": "full" if online else "offline",
        "features": {
            "describe": True,
            "find": online,
            "read": online,
            "navigate": True,
            "detect": True
        }
    })


# ── Describe ──────────────────────────────────────────────────
@app.route('/describe', methods=['POST'])
def describe():
    data = request.json
    image_b64 = compress_image(data['image'])
    cache_key = cache.make_key(image_b64, 'describe')

    cached = cache.get(cache_key)
    if cached:
        return jsonify({"result": cached, "cached": True})

    image = base64_to_image(image_b64)
    img_np = np.array(image)

    if not has_internet():
        detections = detect_objects(img_np)
        result = format_detections(detections)
        cache.set(cache_key, result)
        return jsonify({"result": result, "cached": False, "offline": True})

    result = describe_scene(img_np, image_b64, call_steve)
    cache.set(cache_key, result)
    return jsonify({"result": result, "cached": False})


# ── Find ──────────────────────────────────────────────────────
@app.route('/find', methods=['POST'])
def find():
    data = request.json
    image_b64 = compress_image(data['image'])
    object_name = data.get('object', 'object')
    cache_key = cache.make_key(image_b64, f'find_{object_name}')

    cached = cache.get(cache_key)
    if cached:
        return jsonify({"result": cached, "cached": True})

    result = find_object(image_b64, object_name, call_steve, has_internet())
    cache.set(cache_key, result)
    return jsonify({"result": result, "cached": False})


# ── Read ──────────────────────────────────────────────────────
@app.route('/read', methods=['POST'])
def read():
    data = request.json
    image_b64 = compress_image(data['image'])
    cache_key = cache.make_key(image_b64, 'read')

    cached = cache.get(cache_key)
    if cached:
        return jsonify({"result": cached, "cached": True})

    image = base64_to_image(image_b64)
    processed = preprocess_for_ocr(image)
    result = read_text(image_b64, processed, call_steve, has_internet())

    cache.set(cache_key, result)
    return jsonify({"result": result, "cached": False})


# ── Navigate ──────────────────────────────────────────────────
@app.route('/navigate', methods=['POST'])
def navigate():
    data = request.json
    image_b64 = compress_image(data['image'])
    cache_key = cache.make_key(image_b64, 'navigate')

    cached = cache.get(cache_key)
    if cached:
        return jsonify({"result": cached, "cached": True})

    image = base64_to_image(image_b64)
    img_np = np.array(image)
    result = navigate_scene(img_np, image_b64, call_steve, has_internet())

    cache.set(cache_key, result)
    return jsonify({"result": result, "cached": False})


# ── Detect ────────────────────────────────────────────────────
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
    detections = detect_objects(img_np)
    result = format_detections(detections)

    cache.set(cache_key, result)
    return jsonify({"result": result, "cached": False})


@app.route('/transcribe', methods=['POST'])
def transcribe():
    import tempfile
    data = request.json
    audio_b64 = data.get('audio', '')
    
    if not audio_b64:
        return jsonify({"error": "No audio provided"}), 400

    # Decode base64 audio to temp file
    audio_bytes = base64.b64decode(audio_b64)
    with tempfile.NamedTemporaryFile(suffix='.m4a', delete=False) as f:
        f.write(audio_bytes)
        temp_path = f.name

    try:
        client = Groq(api_key=os.getenv('GROQ_API_KEY'))
        with open(temp_path, 'rb') as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file,
                language="en"
            )
        return jsonify({"text": transcription.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        os.unlink(temp_path)

# ── Command router ────────────────────────────────────────────
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
        return read()
    elif intent['intent'] == 'navigate':
        return navigate()
    elif intent['intent'] == 'detect':
        return detect()
    elif intent['intent'] == 'find':
        request.json['object'] = intent.get('object', 'object')
        return find()


# ── WebSocket ─────────────────────────────────────────────────
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
            else:
                image = base64_to_image(image_b64)
                img_np = np.array(image)
                online = has_internet()

                if action == 'describe':
                    if online:
                        result = describe_scene(img_np, image_b64, call_steve)
                    else:
                        result = format_detections(detect_objects(img_np))
                elif action == 'read':
                    processed = preprocess_for_ocr(image)
                    result = read_text(image_b64, processed, call_steve, online)
                elif action == 'find':
                    obj = data.get('object', 'object')
                    result = find_object(image_b64, obj, call_steve, online)
                elif action == 'navigate':
                    result = navigate_scene(img_np, image_b64, call_steve, online)
                elif action == 'detect':
                    result = format_detections(detect_objects(img_np))
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

    print("📱 Client disconnected")


# ── Run ───────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'True') == 'True'
    online = has_internet()
    print(f"🚀 VisionAid backend running on port {port}")
    print(f"🤖 AI: Groq Llama4 Scout (Free)")
    print(f"📖 OCR: Tesseract (Offline) + Groq (Online)")
    print(f"🎯 Detection: YOLO11x (Offline)")
    print(f"🌐 Internet: {'✅ Online' if online else '❌ Offline — YOLO only'}")
    print(f"📡 WebSocket: ws://localhost:{port}/ws")
    app.run(host='0.0.0.0', port=port, debug=debug)