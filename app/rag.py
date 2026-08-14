"""RAG (Retrieval-Augmented Generation) sobre normativa ambiental.

Arquitectura:
1. Al arrancar, se parte el documento fuente en fragmentos ("chunks") por
   artículo/sección.
2. Cada fragmento se convierte en un vector (embedding) usando la API de
   embeddings de Gemini — se reutiliza la misma GEMINI_API_KEY que ya usa
   el proyecto `reporte-cuadrillas`, sin necesidad de librerías pesadas
   (torch/sentence-transformers) que no caben cómodamente en el plan
   gratuito de Render.
3. Ante una pregunta, se embebe la pregunta con el mismo modelo, se busca
   por similitud coseno los fragmentos más relevantes, y se le pasan a
   Claude como contexto para que responda citando el artículo exacto.
"""
import logging
import re
import time

import httpx
import numpy as np

from app.config import settings

logger = logging.getLogger("uvicorn.error")

EMBED_MODEL = "models/text-embedding-004"
EMBED_URL = f"https://generativelanguage.googleapis.com/v1beta/{EMBED_MODEL}:embedContent"

ERRORES_TRANSITORIOS = (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)


def _con_reintentos(func, intentos: int = 3, espera_base: float = 1.5):
    for intento in range(1, intentos + 1):
        try:
            return func()
        except ERRORES_TRANSITORIOS as e:
            if intento == intentos:
                raise
            espera = espera_base * intento
            logger.warning(f"RAG: intento {intento}/{intentos} falló ({type(e).__name__}); reintentando en {espera:.1f}s")
            time.sleep(espera)


def _embeber(texto: str, tarea: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    """Convierte un texto en un vector usando la API de embeddings de Gemini."""
    def _llamar():
        return httpx.post(
            EMBED_URL,
            headers={"x-goog-api-key": settings.GEMINI_API_KEY},
            json={
                "model": EMBED_MODEL,
                "content": {"parts": [{"text": texto}]},
                "taskType": tarea,
            },
            timeout=20,
        )

    r = _con_reintentos(_llamar)
    r.raise_for_status()
    return r.json()["embedding"]["values"]


def _partir_en_fragmentos(texto: str) -> list[dict]:
    """Divide el documento en fragmentos por artículo (separados por '===')."""
    bloques = [b.strip() for b in texto.split("===") if b.strip()]
    fragmentos = []
    for b in bloques:
        m = re.match(r"ARTÍCULO\s+(\d+)", b)
        titulo = f"Artículo {m.group(1)}" if m else "Introducción / Nota"
        fragmentos.append({"titulo": titulo, "texto": b})
    return fragmentos


class IndiceNormativa:
    """Índice en memoria: fragmentos + sus embeddings, listo para búsqueda."""

    def __init__(self):
        self.fragmentos: list[dict] = []
        self.embeddings: np.ndarray | None = None
        self.listo = False

    def construir(self, ruta_documento: str):
        with open(ruta_documento, encoding="utf-8") as f:
            texto = f.read()

        self.fragmentos = _partir_en_fragmentos(texto)
        logger.info(f"RAG: indexando {len(self.fragmentos)} fragmentos de normativa...")

        vectores = []
        for frag in self.fragmentos:
            try:
                vectores.append(_embeber(frag["texto"]))
            except Exception as e:
                logger.error(f"RAG: no se pudo indexar '{frag['titulo']}': {e}")
                vectores.append(None)

        # Descartar fragmentos que no se pudieron embeber
        validos = [(f, v) for f, v in zip(self.fragmentos, vectores) if v is not None]
        self.fragmentos = [f for f, _ in validos]
        self.embeddings = np.array([v for _, v in validos], dtype=np.float32)
        self.listo = len(self.fragmentos) > 0
        logger.info(f"RAG: índice listo con {len(self.fragmentos)} fragmentos.")

    def buscar(self, pregunta: str, top_k: int = 3) -> list[dict]:
        if not self.listo:
            return []
        vector_pregunta = np.array(_embeber(pregunta, tarea="RETRIEVAL_QUERY"), dtype=np.float32)
        # similitud coseno
        normas = np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(vector_pregunta)
        similitudes = (self.embeddings @ vector_pregunta) / np.where(normas == 0, 1e-8, normas)
        indices = np.argsort(-similitudes)[:top_k]
        return [
            {**self.fragmentos[i], "similitud": float(similitudes[i])}
            for i in indices
        ]


indice = IndiceNormativa()


PROMPT_SISTEMA = """Eres un asistente de cumplimiento ambiental para ingenieros de \
campo en el sector de hidrocarburos en Colombia. Respondes preguntas basándote \
ÚNICAMENTE en los fragmentos de normativa que se te entregan a continuación.

Reglas:
- Si la normativa entregada no contiene la respuesta, dilo claramente: "La \
normativa que tengo disponible no cubre esto" — nunca inventes valores ni artículos.
- Cita siempre el número de artículo exacto de donde sale tu respuesta.
- Sé directo y práctico: el usuario te está escribiendo desde el campo por WhatsApp.
- Aclara siempre que esto no sustituye asesoría legal/ambiental profesional ni \
los procedimientos internos oficiales de la empresa.
- Responde en español, en máximo 6-8 líneas.
"""


def responder_pregunta(pregunta: str) -> str:
    """Pipeline completo: busca contexto relevante y genera la respuesta con Claude."""
    import anthropic

    fragmentos = indice.buscar(pregunta, top_k=3)
    if not fragmentos:
        return ("⚠️ El asistente todavía no tiene la normativa indexada, o no "
                "encontró nada relevante para tu pregunta.")

    contexto = "\n\n".join(f"[{f['titulo']}]\n{f['texto']}" for f in fragmentos)

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def _llamar():
        return client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=PROMPT_SISTEMA,
            messages=[{
                "role": "user",
                "content": f"NORMATIVA DISPONIBLE:\n{contexto}\n\nPREGUNTA: {pregunta}",
            }],
        )

    errores_claude = (anthropic.APIConnectionError, anthropic.APITimeoutError,
                       anthropic.InternalServerError)
    for intento in range(1, 4):
        try:
            respuesta = _llamar()
            break
        except errores_claude as e:
            if intento == 3:
                raise
            time.sleep(1.5 * intento)

    return respuesta.content[0].text
