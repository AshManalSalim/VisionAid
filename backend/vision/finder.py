def build_find_prompt(object_name):
    """Build Groq prompt for object finding"""
    return (
        f"Is there a {object_name} visible in this image? "
        "If yes, say exactly where: left side, right side, center, "
        "near, or far. If no, say it is not visible. "
        "Maximum 1 sentence. Be direct."
    )


def find_object(image_b64, object_name, call_ai, has_internet):
    """Find a specific object in the image"""
    if not has_internet:
        return "Find feature requires internet connection."

    prompt = build_find_prompt(object_name)
    return call_ai(image_b64, prompt, max_tokens=100)