import json
import re
from datetime import datetime
from typing import Optional, List

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config.settings import client, OPENAI_MODEL
from app.utils.media_utils import (
    bytes_to_data_url,
    pdf_to_data_urls,
    build_message_content,
)

SYSTEM_PROMPT_ANOTACION = """Eres un extractor experto de documentos SUNARP (Perú).
Analiza la imagen de una ANOTACIÓN DE INSCRIPCIÓN y devuelve SOLO JSON (sin texto adicional).

Reglas:
- No inventes datos: si un valor no está visible → null.
- Montos como string con 2 decimales. Ej: "320.00".
- Fechas en formato dd/MM/yyyy.
- No calcules montos, solo extrae lo impreso.

Esquema esperado:
{
  "documentType": "anotacion_inscripcion",
  "data": {
    "anioTitulo": string|null,
    "numeroTitulo": string|null,
    "oficinaRegistral": string|null,
    "seccionRegistral": string|null,
    "numeroPartida": string|null,
    "fechaPresentacion": string|null,
    "montoInscripcion": string|null,
    "montoDevolucion": string|null,
    "fechaInscripcion": string|null,
    "nombreRegistrador": string|null
  }
}

Pistas:
- “TITULO N° : aaaa-nnnnnnn” → año y número de título.
- “OFICINA REGISTRAL ...” arriba.
- “PARTIDA N° xxxxxxxx” en el bloque del ACTO.
- “Fecha de Presentación : dd/mm/aaaa” junto al título.
- “Derechos pagados : S/ xxx.xx” => montoInscripcion.
- “Derechos por devolver : S/ xx.xx” => montoDevolucion.
- La fecha final aparece como “CIUDAD, 24 de Octubre de 2025.” (convierte a dd/MM/yyyy).
- El nombre del Registrador está en la firma inferior.
"""

# ---------- Modelos de salida ----------
class AnotacionData(BaseModel):
    anioTitulo: Optional[str] = None
    numeroTitulo: Optional[str] = None
    oficinaRegistral: Optional[str] = None
    seccionRegistral: Optional[str] = None
    numeroPartida: Optional[str] = None
    fechaPresentacion: Optional[str] = None
    montoInscripcion: Optional[str] = None
    montoDevolucion: Optional[str] = None
    fechaInscripcion: Optional[str] = None
    nombreRegistrador: Optional[str] = None

class AnotacionOut(BaseModel):
    documentType: str = Field(default="anotacion_inscripcion")
    data: AnotacionData = Field(default_factory=AnotacionData)

# ---------- Utilidades de normalización ----------
_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12
}

def norm_amount(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    raw = s.strip().upper().replace("S/.", "").replace("S/", "").replace("SOLES", "").strip()
    # 1.234,56 -> 1234.56 ; 1,234.56 -> 1234.56 ; 320.00 -> 320.00
    if raw.count(',') == 1 and raw.count('.') >= 1:
        pass  # en-US
    elif raw.count(',') == 1 and raw.count('.') == 0:
        raw = raw.replace('.', '').replace(',', '.')
    else:
        raw = raw.replace(',', '')
    try:
        return f"{float(raw):.2f}"
    except Exception:
        return None

_DATE_RX = re.compile(r'(\d{1,2})[\/\-. ](\d{1,2})[\/\-. ](\d{2,4})')

def norm_date_ddmmyyyy(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    # Caso “24 de Octubre de 2025”
    mtxt = re.search(r'(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóú]+)\s+de\s+(\d{4})', s, re.IGNORECASE)
    if mtxt:
        d, month_name, y = mtxt.groups()
        mn = _MONTHS.get(month_name.lower(), None)
        if mn:
            try:
                return datetime(int(y), int(mn), int(d)).strftime("%d/%m/%Y")
            except Exception:
                pass
    # Caso dd/mm/yyyy
    m = _DATE_RX.search(s)
    if m:
        d, mn, y = m.groups()
        if len(y) == 2:
            y = '20' + y if int(y) < 50 else '19' + y
        try:
            return datetime(int(y), int(mn), int(d)).strftime("%d/%m/%Y")
        except Exception:
            return None
    return None

def _repair_json_block(txt: str) -> dict:
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        start = txt.find('{'); end = txt.rfind('}')
        if start != -1 and end != -1:
            return json.loads(txt[start:end+1])
        raise

# ---------- Controlador ----------
async def extract_anotacion(file_content: bytes, content_type: str, model_override: Optional[str], max_pages: int):
    """
    Extrae JSON desde 'Anotación de Inscripción' (imagen o PDF).
    """
    is_pdf = (content_type.lower() == "application/pdf")
    is_img = content_type.lower().startswith("image/")
    if not (is_pdf or is_img):
        raise HTTPException(status_code=400, detail="Sube una imagen (jpg/png) o un PDF.")

    # Render a imágenes (data URLs)
    if is_pdf:
        image_urls: List[str] = pdf_to_data_urls(file_content, max_pages=max_pages, dpi=200)
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
                "content": build_message_content(SYSTEM_PROMPT_ANOTACION, image_urls)
            }]
        )
        json_text = chat.choices[0].message.content or "{}"
        raw_data = _repair_json_block(json_text)

        # Validación y saneo
        validated = AnotacionOut(**raw_data)

        # Normalizaciones
        d = validated.data
        d.montoInscripcion = norm_amount(d.montoInscripcion)
        d.montoDevolucion  = norm_amount(d.montoDevolucion)
        d.fechaPresentacion = norm_date_ddmmyyyy(d.fechaPresentacion)
        d.fechaInscripcion  = norm_date_ddmmyyyy(d.fechaInscripcion)

        return JSONResponse(validated.model_dump())

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Extractor anotación falló: {e.__class__.__name__}: {str(e)[:500]}"
        )
