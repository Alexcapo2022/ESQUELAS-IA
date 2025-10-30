from fastapi import FastAPI
from app.routes.extract_routes import router as extract_router
from app.config.settings import OPENAI_MODEL

app = FastAPI(title="Extracción Esquelas SUNARP (IA)", version="2.0.0")

@app.get("/health")
def health():
    return {"ok": True, "model": OPENAI_MODEL}

# Montar rutas
app.include_router(extract_router)
