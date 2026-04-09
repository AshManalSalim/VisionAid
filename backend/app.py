import os
import json
import time
import base64
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

# ── Health ────────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "ai": "groq-llama4-scout",
        "ocr": "tesseract",
        "timestamp": time.time(),
        "cache_size": cache.size()
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

    prompt = (
        f"Is there a {object_name} visible in this image? "
        "If yes, say exactly where: left side, right side, center, "
        "near, or far. If no, say it is not visible. "
        "Maximum 1 sentence. Be direct."
    )
    result = call_steve(image_b64, prompt, max_tokens=100)
    cache.set(cache_key, result)
    return jsonify({"result": result, "cached": False})

# ── Read ──────────────────────────────────────────────────────
@app.route('/read', methods=['POST'])
def read_text():
    data = request.json
    image_b64 = compress_image(data['image'])
    cache_key = cache.make_key(image_b64, 'read')

    cached = cache.get(cache_key)
    if cached:
        return jsonify({"result": cached, "cached": True})

    image = base64_to_image(image_b64)
    processed = preprocess_for_ocr(image)

    text = pytesseract.image_to_string(
        processed,
        config='--psm 6 --oem 3'
    ).strip()

    result = text if text else "No text detected"
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
        return read_text()
    elif intent['intent'] == 'navigate':
        return navigate()
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
    print(f" VisionAid backend running on port {port}")
    print(f" AI: Groq Llama4 Scout (Free)")
    print(f" OCR: Tesseract (Offline)")
    print(f" WebSocket available at ws://localhost:{port}/ws")
    app.run(host='0.0.0.0', port=port, debug=debug)