import os
import json
import time
import threading 

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sock import Sock
from dotenv import load_dotenv
import google.generativeai as genai


from utils.image import compress_image, base64_to_image, preprocess_for_ocr
from utils.cache import cache
from voice.intent import parse_intent, get_help_text

load_dotenv()

app = Flask(__name__)
CORS(app)
sock = Sock(app)

# ── Configure Gemini ─────────────────────────────────────────────────────────
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

_ocr_reader = None

def get_ocr():
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        _ocr_reader = easyocr.Reader(['en'], gpu=False)
    return _ocr_reader



def call_steve(image_b64, prompt, max_tokens=300):
    """Send image + prompt to Gemini and return response text"""
    import base64
    
    image_data = base64.b64decode(image_b64)
    
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=[
            types.Part.from_bytes(
                data=image_data,
                mime_type='image/jpeg'
            ),
            prompt
        ],
        config=types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=0.3
        )
    )
    
    return response.text

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "ai": "gemini-2.0-flash",
        "timestamp": time.time(),
        "cache_size": cache.size()
    })


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
        "top, bottom, near, or far. "
        "If no, say it is not visible. "
        "Maximum 1 sentence. Be direct."
    )
    result = call_steve(image_b64, prompt, max_tokens=100)
    cache.set(cache_key, result)
    return jsonify({"result": result, "cached": False})


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
    import numpy as np
    results = get_ocr().readtext(np.array(processed))

    if results:
        text = ' '.join([r[1] for r in results if r[2] > 0.3])
        result = text if text.strip() else "No readable text found"
    else:
        result = "No text detected in the image"

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
        "Analyze the path ahead and answer: "
        "1. Is the path clear to walk? "
        "2. Are there any obstacles? If yes, where exactly and how close? "
        "3. What surface is ahead (floor, stairs, road)? "
        "Be very concise, max 2 sentences. Start with CLEAR or WARNING."
    )
    result = call_steve(image_b64, prompt, max_tokens=150)
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
    print(" Client connected via WebSocket")

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

            ws.send(json.dumps({
                "status": "processing",
                "action": action
            }))

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
                import numpy as np
                results = get_ocr().readtext(np.array(processed))
                result = ' '.join([r[1] for r in results if r[2] > 0.3]) or "No text found"
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

    print(" Client disconnected")


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'True') == 'True'
    print(f"VisionAid backend running on port {port}")
    print(f"AI: Gemini 1.5 Flash ")
    print(f"WebSocket available at ws://localhost:{port}/ws")
    app.run(host='0.0.0.0', port=port, debug=debug)