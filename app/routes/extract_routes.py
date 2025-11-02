from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from app.controllers.inscrito_controller import extract_anotacion
from app.controllers.liquidado_controller import extract_liquidado
from app.controllers.observado_controller import extract_observado

router = APIRouter(prefix="/api/extract", tags=["extract"])

@router.post("/liquidado")
async def extract_liquidado_route(
    file: UploadFile = File(...),
    model: str | None = Query(default=None, description="Override del modelo (opcional)"),
    max_pages: int = Query(default=3, ge=1, le=10, description="Máx páginas PDF a procesar (1-10)")
):
    if not file.content_type:
        raise HTTPException(status_code=400, detail="No se pudo detectar el content-type del archivo.")

    raw = await file.read()
    return await extract_liquidado(raw, file.content_type, model, max_pages)

@router.post("/inscrito")
async def extract_anotacion_route(
    file: UploadFile = File(...),
    model: str | None = Query(default=None),
    max_pages: int = Query(default=3, ge=1, le=10)
):
    if not file.content_type:
        raise HTTPException(status_code=400, detail="No se pudo detectar el content-type del archivo.")
    raw = await file.read()
    return await extract_anotacion(raw, file.content_type, model, max_pages)


@router.post("/observado")
async def extract_observado_route(
    file: UploadFile = File(...),
    model: str | None = Query(default=None),
    max_pages: int = Query(default=3, ge=1, le=10)
):
    if not file.content_type:
        raise HTTPException(status_code=400, detail="No se pudo detectar el content-type del archivo.")
    raw = await file.read()
    return await extract_observado(raw, file.content_type, model, max_pages)