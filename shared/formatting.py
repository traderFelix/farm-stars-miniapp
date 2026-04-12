def fmt_stars(value: float) -> str:
    text = f"{float(value):.2f}"
    text = text.rstrip("0").rstrip(".")
    return text if text else "0"
