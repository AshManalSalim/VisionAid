from vision.detector import detect_objects


def build_describe_prompt(detections):
    if detections:
        yolo_context = ", ".join(detections[:10])
        return (
            f"You are an assistant for a blind person. "
            f"YOLO object detection found: {yolo_context}. "
            f"Using this information and the image, give a clear natural "
            f"2 sentence description of what's ahead. "
            f"Mention the most important objects and any dangers. "
            f"Be specific about distances and directions. "
            f"Use simple clear language. "
            f"Always use metric units (meters, centimeters). Never use feet or inches."
        )
    return (
        "You are an assistant for a blind person. "
        "In 2 short sentences describe what is directly ahead "
        "and warn about any obstacles. "
        "Be specific about distances. Use simple clear language. "
        "Always use metric units (meters, centimeters). Never use feet or inches."
    )


def build_navigate_prompt():
    return (
        "You are a navigation assistant for a blind person. "
        "Is the path ahead clear to walk? "
        "Are there any obstacles? If yes, where and how close? "
        "What surface is ahead? "
        "Be concise, max 2 sentences. Start with CLEAR or WARNING. "
        "Always use metric units (meters, centimeters). Never use feet or inches."
    )

def describe_scene(img_np, image_b64, call_ai):
    """
    Describe scene using YOLO + Groq combined.
    call_ai is the function to call the AI model.
    """
    detections = detect_objects(img_np)
    prompt = build_describe_prompt(detections)
    return call_ai(image_b64, prompt)


def navigate_scene(img_np, image_b64, call_ai, has_internet):
    """Navigate scene - uses Groq online, YOLO offline"""
    if not has_internet:
        from vision.detector import format_detections, has_danger
        detections = detect_objects(img_np)
        result = format_detections(detections)
        return "WARNING! " + result if has_danger(detections) else "CLEAR. " + result

    prompt = build_navigate_prompt()
    return call_ai(image_b64, prompt, max_tokens=150)