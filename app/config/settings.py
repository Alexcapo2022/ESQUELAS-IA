import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

if not OPENAI_API_KEY:
    raise RuntimeError("Falta OPENAI_API_KEY en .env o variables de entorno.")

# Cliente OpenAI (singleton simple)
client = OpenAI(api_key=OPENAI_API_KEY)
