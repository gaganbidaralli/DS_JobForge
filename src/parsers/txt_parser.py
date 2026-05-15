"""Extract text from plain-text files."""


def extract_text_txt(file_path: str) -> str:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(file_path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Cannot decode: {file_path}")
