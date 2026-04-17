import numpy as np

_yolo_model = None


def get_yolo():
    """Lazy load YOLO model"""
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        _yolo_model = YOLO('yolo11x.pt')
    return _yolo_model


def get_position(x_center, img_width):
    """Get object position based on x coordinate"""
    if x_center < img_width / 3:
        return "to your left"
    elif x_center > 2 * img_width / 3:
        return "to your right"
    return "in front of you"


def get_distance(box_area, img_area):
    ratio = box_area / img_area
    if ratio > 0.15:
        return "very close"
    elif ratio > 0.05:
        return "nearby"
    elif ratio > 0.02:
        return "a few meters away"
    else:
        return "far away"


def detect_objects(img_np, confidence_threshold=0.3, max_objects=10):
    """
    Run YOLO detection on image.
    Returns list of detection strings like 'chair to your left nearby'
    """
    model = get_yolo()
    results = model(img_np, verbose=False)
    detections = []

    for result in results:
        for box in result.boxes[:max_objects]:
            cls_id = int(box.cls[0])
            confidence = float(box.conf[0])
            label = result.names[cls_id]

            if confidence < confidence_threshold:
                continue

            x_center = float(box.xywh[0][0])
            img_width = img_np.shape[1]
            position = get_position(x_center, img_width)

            box_area = float(box.xywh[0][2] * box.xywh[0][3])
            img_area = img_np.shape[0] * img_np.shape[1]
            distance = get_distance(box_area, img_area)

            detections.append(f"{label} {position} {distance}")

    return detections


def format_detections(detections):
    """Format detections list into readable string"""
    if not detections:
        return "No objects detected in the scene"
    count = len(detections)
    return f"I can see {count} object{'s' if count > 1 else ''}: " + ", ".join(detections[:10])


def has_danger(detections):
    """Check if any detection is very close (dangerous)"""
    return any("very close" in d for d in detections)