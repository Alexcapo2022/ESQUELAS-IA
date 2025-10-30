import json
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from . import __init__  # noqa: F401
from app.config.settings import client, OPENAI_MODEL
from app.utils.media_utils import bytes_to_data_url, pdf_to_data_urls, build_message_content

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

async def extract_liquidado(file_content: bytes, content_type: str, model_override: str | None, max_pages: int):
    """
    Lógica de negocio para extraer JSON de 'Esquela de Liquidación'.
    Acepta imagen o PDF. Si PDF -> se convierte a imágenes.
    """
    is_pdf = (content_type.lower() == "application/pdf")
    is_img = content_type.lower().startswith("image/")

    if not (is_pdf or is_img):
        raise HTTPException(status_code=400, detail="Sube una imagen (jpg/png) o un PDF.")

    # Prepara data URLs
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

        json_text = chat.choices[0].message.content
        data = json.loads(json_text)

        # Saneos básicos
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
        raise HTTPException(status_code=500, detail=str(e))
