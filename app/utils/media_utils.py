import base64
from typing import List

def bytes_to_data_url(raw: bytes, mime: str) -> str:
    b64 = base64.b64encode(raw).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def pdf_to_data_urls(pdf_bytes: bytes, max_pages: int = 3, dpi: int = 200) -> List[str]:
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise RuntimeError("PyMuPDF (fitz) no está instalado. Agrega 'PyMuPDF' a requirements.txt e instala.") from e

    urls: List[str] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        page_count = min(len(doc), max_pages)
        for i in range(page_count):
            page = doc.load_page(i)
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("png")
            urls.append(bytes_to_data_url(img_bytes, "image/png"))
    return urls

def build_message_content(system_prompt: str, images: List[str]) -> list[dict]:
    content: list[dict] = [{"type": "text", "text": system_prompt}]
    for url in images:
        content.append({"type": "image_url", "image_url": {"url": url}})
    return content
