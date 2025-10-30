```markdown
# 🧠 Extracción de Esquelas SUNARP (IA)

Proyecto **FastAPI + OpenAI Vision** para extraer automáticamente datos estructurados (JSON) desde **imágenes o PDFs** de *Esquelas de Liquidación* de SUNARP.

---

## 🚀 Tecnologías
- **Python 3.10+**
- **FastAPI** (API REST)
- **OpenAI GPT-4o / GPT-4o-mini** (modelos con visión)
- **PyMuPDF (fitz)** para procesar PDFs
- **Uvicorn** como servidor ASGI

---

## 🗂️ Estructura del proyecto
```

app/
├─ main.py
├─ routes/
│  └─ extract_routes.py
├─ controllers/
│  └─ liquidado_controller.py
├─ utils/
│  └─ media_utils.py
└─ config/
└─ settings.py
.env
requirements.txt

````

---

## ⚙️ Instalación rápida

```bash
# 1. Clonar o copiar
git clone <URL_DEL_REPO>
cd extraccion-esquelas-ia

# 2. Crear entorno virtual
python -m venv .venv
.venv\Scripts\activate   # Windows
# o
source .venv/bin/activate  # macOS / Linux

# 3. Instalar dependencias
pip install -r requirements.txt
````

**Archivo `.env`**

```
OPENAI_API_KEY=sk-xxxx_tu_clave
OPENAI_MODEL=gpt-4o-mini
APP_HOST=127.0.0.1
APP_PORT=8000
```

---

## ▶️ Ejecutar servidor

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

* Acceso local: [http://127.0.0.1:8000](http://127.0.0.1:8000)
* Healthcheck: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## 📤 Endpoints principales

### `/api/extract/liquidado`

**POST** → recibe una imagen o PDF de una esquela y devuelve un JSON estructurado.

**Parámetros**

* `file`: archivo (imagen o PDF)
* `model` (opcional): sobreescribe modelo (`gpt-4o`, `gpt-4o-mini`)
* `max_pages` (opcional): cantidad de páginas a procesar en PDFs (por defecto 3)

---

## 🧩 Ejemplo de salida

```json
{
  "documentType": "esquela_liquidacion",
  "data": {
    "anioTitulo": "2025",
    "numeroTitulo": "02947707",
    "oficinaRegistral": "CHIMBOTE",
    "fechaPresentacion": "02/10/2025",
    "horaPresentacion": "13:42:25",
    "fechaVencimiento": "06/01/2026",
    "fechaLiquidacion": "16/10/2025",
    "derechosRegistrales": "901.90",
    "pagoCuenta": "130.00",
    "diferenciaPorPagar": "771.90",
    "nombreRegistrador": "CARMEN BEATRIZ GONZA Y DIAQUEZ"
  }
}
```

---

## 🧠 Próximos pasos

* Agregar nuevos tipos de extracción (`/api/extract/observacion`, `/api/extract/ingreso`, etc.)
* Implementar Dockerfile y logging
* Integrar autenticación (JWT / API Key)

---

## 👨‍💻 Autor

**Proyecto Interno Alexander Cruz**
Desarrollo IA — *Automatización de procesos registrales SUNARP*

```
```
