import google.generativeai as genai
import os
from dotenv import load_dotenv
import base64
import requests

load_dotenv()

genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

def test_gemini_text():
    print("🧪 Test 1: Basic Gemini text...")
    model = genai.GenerativeModel('gemini-2.0-flash')
    response = model.generate_content("Say hello in one sentence.")
    print(f"✅ Gemini says: {response.text}")

def test_gemini_image():
    print("\n🧪 Test 2: Gemini Vision...")
    import urllib.request
    urllib.request.urlretrieve(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png",
        "test_image.png"
    )
    with open("test_image.png", "rb") as f:
        image_data = f.read()
    image_b64 = base64.b64encode(image_data).decode('utf-8')
    model = genai.GenerativeModel('gemini-2.0-flash')
    response = model.generate_content([
        {"mime_type": "image/png", "data": base64.b64decode(image_b64)},
        "Describe this image in one sentence as if talking to a blind person."
    ])
    print(f"✅ Gemini Vision says: {response.text}")

def test_server_health():
    print("\n🧪 Test 3: Server health check...")
    try:
        response = requests.get("http://localhost:5000/health")
        print(f"✅ Server status: {response.json()}")
    except:
        print("❌ Server not running! Start it with: python app.py")

def test_server_describe():
    print("\n🧪 Test 4: Server /describe endpoint...")
    try:
        with open("test_image.png", "rb") as f:
            image_data = f.read()
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        response = requests.post(
            "http://localhost:5000/describe",
            json={"image": image_b64}
        )
        result = response.json()
        print(f"✅ Description: {result['result']}")
        print(f"   Cached: {result['cached']}")
    except Exception as e:
        print(f"❌ Error: {e}")

def test_cache():
    print("\n🧪 Test 5: Cache test...")
    with open("test_image.png", "rb") as f:
        image_data = f.read()
    image_b64 = base64.b64encode(image_data).decode('utf-8')
    import time
    start = time.time()
    response1 = requests.post("http://localhost:5000/describe", json={"image": image_b64})
    time1 = time.time() - start
    start = time.time()
    response2 = requests.post("http://localhost:5000/describe", json={"image": image_b64})
    time2 = time.time() - start
    print(f"   First call:  {time1:.2f}s (cached: {response1.json()['cached']})")
    print(f"   Second call: {time2:.2f}s (cached: {response2.json()['cached']})")
    if time2 < time1:
        print("✅ Cache is working!")
    else:
        print("⚠️ Cache might not be working.")

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 VisionAid - Gemini Integration Tests")
    print("=" * 50)
    test_gemini_text()
    test_gemini_image()
    test_server_health()
    test_server_describe()
    test_cache()
    print("\n" + "=" * 50)
    print("✅ All tests complete!")
    print("=" * 50)