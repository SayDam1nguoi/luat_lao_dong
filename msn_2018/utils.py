def detect_vsic_level(code: str) -> str:
    if not code:
        return "unknown"

    if code.isalpha():
        return "section"

    if code.isdigit():
        if len(code) == 2:
            return "division"
        if len(code) == 3:
            return "group"
        if len(code) == 4:
            return "class"
        if len(code) == 5:
            return "subclass"

    return "unknown"
