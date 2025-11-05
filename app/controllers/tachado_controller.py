import json
import re
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.config.settings import client, OPENAI_MODEL
from app.utils.media_utils import bytes_to_data_url, pdf_to_data_urls, build_message_content

SYSTEM_PROMPT = """Eres un extractor experto de documentos SUNARP (Perú).
Analiza una ESQUELA DE Tacha (tacha especial / tacha por caducidad) y devuelve SOLO JSON.

Reglas:
- NUNCA incluyas texto fuera del JSON.
- Si un dato no está visible, usa null (no inventes).
- Formato objetivo: numero de título como string tal cual aparece (aaaa-nnnnnnnn).
- 'Derechos por devolver' como monto string con 2 decimales (ej: "37.20").

Esquema objetivo:
{
  "documentType": "tacha",
  "data": {
    "numeroTitulo": string|null,
    "derechosPorDevolver": string|null
  }
}

Pistas de extracción:
- Encabezado suele decir: "TACHA ...", "TACHA POR CADUCIDAD...", etc.
- Número de título aparece como: "Número de título : aaaa-nnnnnnnn".
- Monto devolver aparece como: "Derechos por devolver : S/ xx.xx".
- Ignora otros montos (pagados, cobrados). SOLAMENTE 'Derechos por devolver'.
"""

def _to_float_2(monto: str | None) -> float:
    if not monto:
        return 0.0
    s = monto.strip()

    # Normalizaciones frecuentes: "S/ 37.20 soles", "S/. 37,20", "S/37.20"
    s = s.replace("S/.", "S/").replace("s/.", "s/").replace("soles", "").replace("SOLes", "")
    # Conserva dígitos y separador decimal (coma o punto)
    s = re.sub(r"[^0-9,\.]", "", s)
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    # Si quedaron múltiples puntos, quita todo menos el último
    if s.count(".") > 1:
        parts = re.findall(r"\d+", s)
        if len(parts) >= 2:
            s = parts[0] + "." + parts[1]
    try:
        return round(float(s), 2)
    except Exception:
        return 0.0

async def extract_tachado(file_content: bytes, content_type: str, model_override: str | None, max_pages: int):
    is_pdf = (content_type.lower() == "application/pdf")
    is_img = content_type.lower().startswith("image/")
    if not (is_pdf or is_img):
        raise HTTPException(status_code=400, detail="Sube una imagen (jpg/png) o un PDF.")

    # Render a data URLs
    if is_pdf:
        image_urls = pdf_to_data_urls(file_content, max_pages=max_pages, dpi=200)
        if not image_urls:
            raise HTTPException(status_code=500, detail="No se pudieron renderizar páginas del PDF.")
    else:
        mime = content_type or "image/png"
        image_urls = [bytes_to_data_url(file_content, mime)]

    effective_model = model_override or OPENAI_MODEL

    try:
        chat = client.chat.completions.create(
            model=effective_model,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": build_message_content(SYSTEM_PROMPT, image_urls)
            }]
        )
        raw = chat.choices[0].message.content
        data = json.loads(raw)

        # saneo y normalización
        data.setdefault("documentType", "tacha")
        data.setdefault("data", {})
        numero = data["data"].get("numeroTitulo")
        devolver_raw = data["data"].get("derechosPorDevolver")

        devolver_num = _to_float_2(devolver_raw)

        normalized = {
            "documentType": "tacha",
            "data": {
                "numeroTitulo": numero if numero else None,
                "derechosPorDevolver": devolver_num  # decimal; 0.0 si no aparece
            }
        }
        return JSONResponse(normalized)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
