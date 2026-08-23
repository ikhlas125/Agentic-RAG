
def make_json_serializable(obj):
    if isinstance(obj, dict):
        return {key: make_json_serializable(value) for key, value in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [make_json_serializable(value) for value in obj]

    if hasattr(obj, "x0") and hasattr(obj, "y0") and hasattr(obj, "x1") and hasattr(obj, "y1"):
        return [obj.x0, obj.y0, obj.x1, obj.y1]

    return obj

