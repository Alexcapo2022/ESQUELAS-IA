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

SYSTEM_PROMPT_OBSERVADO = """Eres un extractor experto de documentos SUNARP (Perú).
Analiza la imagen de una ESQUELA DE OBSERVACIÓN y devuelve SOLO JSON (sin texto adicional).

Reglas:
- No inventes datos: si un valor no está visible → null.
- Montos como string con 2 decimales. Ej: "8.90".
- Fechas en formato dd/MM/yyyy.
- No calcules montos, solo extrae lo impreso.

Esquema esperado:
{
  "documentType": "esquela_observacion",
  "data": {
    "fechaObservacion": string|null,
    "fechaVencimiento": string|null,
    "montoLiquidado": string|null
  }
}

Pistas:
- “Subsanar y pagar mayor derecho hasta el:” → fechaObservacion.
- “Fecha de vencimiento:” → fechaVencimiento.
- “Derechos pendientes de pago” o “Monto liquidado” → montoLiquidado (ej. “S/ 8.90”).
"""

# --------- Modelos ----------
class ObservadoData(BaseModel):
    fechaObservacion: Optional[str] = None  # dd/MM/yyyy
    fechaVencimiento: Optional[str] = None  # dd/MM/yyyy
    montoLiquidado: Optional[str] = None    # "###.##"

class ObservadoOut(BaseModel):
    documentType: str = Field(default="esquela_observacion")
    data: ObservadoData = Field(default_factory=ObservadoData)

# --------- Normalización ----------
def _norm_amount(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    raw = (
        s.upper()
         .replace("S/.", "")
         .replace("S/", "")
         .replace("SOLES", "")
         .replace(" ", "")
         .strip()
    )
    # 1.234,56 -> 1234.56 ; 1,234.56 -> 1234.56 ; 8.90 -> 8.90
    if raw.count(',') == 1 and raw.count('.') >= 1:
        pass
    elif raw.count(',') == 1 and raw.count('.') == 0:
        raw = raw.replace('.', '').replace(',', '.')
    else:
        raw = raw.replace(',', '')
    try:
        return f"{float(raw):.2f}"
    except Exception:
        return None

_DATE_RX = re.compile(r'(\d{1,2})[\/\-. ](\d{1,2})[\/\-. ](\d{2,4})')
_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12
}

def _norm_date_ddmmyyyy(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    # “16 de octubre de 2025”
    mtxt = re.search(r'(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóú]+)\s+de\s+(\d{4})', s, re.IGNORECASE)
    if mtxt:
        d, month_name, y = mtxt.groups()
        mn = _MONTHS.get(month_name.lower())
        if mn:
            try:
                return datetime(int(y), int(mn), int(d)).strftime("%d/%m/%Y")
            except Exception:
                pass
    # dd/mm/yyyy
    m = _DATE_RX.search(s)
    if m:
        d, mn, y = m.groups()
        if len(y) == 2:
            y = "20"+y if int(y) < 50 else "19"+y
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

# --------- Controller ----------
async def extract_observado(file_content: bytes, content_type: str, model_override: Optional[str], max_pages: int):
    """
    Extrae JSON desde 'Esquela de Observación' (imagen o PDF).
    """
    is_pdf = (content_type.lower() == "application/pdf")
    is_img = content_type.lower().startswith("image/")
    if not (is_pdf or is_img):
        raise HTTPException(status_code=400, detail="Sube una imagen (jpg/png) o un PDF.")

    # Convertir a data URLs
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
                "content": build_message_content(SYSTEM_PROMPT_OBSERVADO, image_urls)
            }]
        )
        json_text = chat.choices[0].message.content or "{}"
        raw_data = _repair_json_block(json_text)

        # Validación y saneo
        validated = ObservadoOut(**raw_data)
        d = validated.data

        d.fechaObservacion = _norm_date_ddmmyyyy(d.fechaObservacion)
        d.fechaVencimiento = _norm_date_ddmmyyyy(d.fechaVencimiento)
        d.montoLiquidado   = _norm_amount(d.montoLiquidado)

        return JSONResponse(validated.model_dump())

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Extractor observado falló: {e.__class__.__name__}: {str(e)[:500]}"
        )
