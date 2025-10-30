import os
import io
import json
import base64
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from openai import OpenAI

# ====== Cargar .env ======
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # modelos con visión: gpt-4o / gpt-4o-mini
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

if not OPENAI_API_KEY:
    raise RuntimeError("Falta OPENAI_API_KEY en .env o en variables de entorno.")

client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI(title="Extracción Esquelas SUNARP (IA) - MVP", version="1.0.0")

# ========= Prompt: la IA hace TODO el formateo =========
SYSTEM_PROMPT = """Eres un extractor experto de documentos SUNARP (Perú).
Analiza la imagen de una ESQUELA DE LIQUIDACIÓN y devuelve SOLO JSON.

Reglas:
- NUNCA incluyas texto fuera del JSON.
- Si un dato no está visible, devuelve null (no inventes).
- Montos como string con 2 decimales (ej: "340.90").
- Fechas dd/MM/yyyy y hora HH:mm:ss.

Esquema objetivo:
{
  "documentType": "esquela_liquidacion",
  "data": {
    "anioTitulo": string|null,
    "numeroTitulo": string|null,
    "oficinaRegistral": string|null,
    "seccionRegistral": string|null,
    "fechaPresentacion": string|null,
    "horaPresentacion": string|null,
    "fechaVencimiento": string|null,
    "fechaLiquidacion": string|null,
    "ultimoDiaPago": string|null,
    "derechosRegistrales": string|null,
    "pagoCuenta": string|null,
    "diferenciaPorPagar": string|null,
    "nombreRegistrador": string|null
  }
}

Pistas de extracción:
- “TÍTULO : aaaa - nnnnnnnn” => anioTitulo, numeroTitulo.
- “Oficina Registral”, “Sección registral”.
- “Fecha de presentación :” contiene fecha y hora.
- “Diferencia por Pagar” está en un recuadro al final.
- “Pago a cuenta Rec. N° …” muestra el monto a la derecha.
- El total de derechos es la suma principal del cuadro de importes.
"""

# ========= Utilidades =========
def bytes_to_data_url(raw: bytes, mime: str) -> str:
    """Convierte bytes a data URL base64."""
    b64 = base64.b64encode(raw).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def pdf_to_data_urls(pdf_bytes: bytes, max_pages: int = 3, dpi: int = 200) -> List[str]:
    """
    Convierte un PDF en una lista de imágenes (data URLs) usando PyMuPDF (fitz).
    max_pages: cuántas páginas como máximo enviar al modelo (para controlar costo).
    dpi: resolución aproximada (200 suele ser suficiente).
    """
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise RuntimeError("PyMuPDF (fitz) no está instalado. Agrega 'PyMuPDF' a requirements.txt e instala.") from e

    data_urls: List[str] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        page_count = min(len(doc), max_pages)
        for i in range(page_count):
            page = doc.load_page(i)
            # Matriz de zoom según DPI (72 base). zoom = dpi/72
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)  # sin canal alpha
            img_bytes = pix.tobytes("png")
            data_urls.append(bytes_to_data_url(img_bytes, "image/png"))
    return data_urls

def build_message_content(images: List[str]) -> List[dict]:
    """
    Construye el array de contenido para Chat Completions con texto + múltiples imágenes.
    """
    content: List[dict] = [{"type": "text", "text": SYSTEM_PROMPT}]
    for url in images:
        content.append({"type": "image_url", "image_url": {"url": url}})
    return content

# ========= Endpoints =========
@app.get("/health")
def health():
    return {"ok": True, "model": OPENAI_MODEL}

@app.post("/extract")
async def extract(
    file: UploadFile = File(...),
    model: str = Query(default=None, description="Override del modelo (opcional, ej: gpt-4o)"),
    max_pages: int = Query(default=3, ge=1, le=10, description="Máx páginas PDF a procesar (1-10)")
):
    """
    Recibe un archivo (imagen o PDF) y devuelve el JSON estructurado.
    - Si es imagen: se envía tal cual.
    - Si es PDF: se convierte cada página a imagen (hasta max_pages) y se envían.
    """
    if not file.content_type:
        raise HTTPException(status_code=400, detail="No se pudo detectar el content-type del archivo.")

    ct = file.content_type.lower()
    is_pdf = (ct == "application/pdf")
    is_img = ct.startswith("image/")

    if not (is_pdf or is_img):
        raise HTTPException(status_code=400, detail="Sube una imagen (jpg/png) o un PDF.")

    raw = await file.read()

    # Prepara las imágenes (data URLs) para el modelo:
    image_urls: List[str] = []
    if is_pdf:
        try:
            image_urls = pdf_to_data_urls(raw, max_pages=max_pages, dpi=200)
            if not image_urls:
                raise RuntimeError("No se pudieron renderizar páginas del PDF.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error convirtiendo PDF a imágenes: {e}")
    else:
        # Imagen directa
        mime = ct or "image/png"
        image_urls = [bytes_to_data_url(raw, mime)]

    # Modelo efectivo: query param > .env
    effective_model = model or OPENAI_MODEL

    try:
        # Llamada a Chat Completions (visión + JSON)
        chat = client.chat.completions.create(
            model=effective_model,
            response_format={"type": "json_object"},  # fuerza JSON válido (no schema)
            messages=[{
                "role": "user",
                "content": build_message_content(image_urls)
            }]
        )

        json_text = chat.choices[0].message.content
        data = json.loads(json_text)

        # saneamos mínimos por si el modelo deja algo vacío
        data.setdefault("documentType", "esquela_liquidacion")
        data.setdefault("data", {})
        for k in [
            "anioTitulo","numeroTitulo","oficinaRegistral","seccionRegistral",
            "fechaPresentacion","horaPresentacion","fechaVencimiento","fechaLiquidacion",
            "ultimoDiaPago","derechosRegistrales","pagoCuenta","diferenciaPorPagar","nombreRegistrador"
        ]:
            data["data"].setdefault(k, None)

        return JSONResponse(data)

    except Exception as e:
        # Propaga mensaje de error útil al cliente
        raise HTTPException(status_code=500, detail=str(e))
