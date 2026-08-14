"""Asistente RAG de cumplimiento ambiental vía WhatsApp."""
import json
import logging
import threading

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, MensajeProcesado, engine, get_db
from app.rag import indice, responder_pregunta
from app.whatsapp import enviar_texto

Base.metadata.create_all(bind=engine)
logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Asistente de Cumplimiento Ambiental")


@app.on_event("startup")
def construir_indice():
    """Indexa la normativa en un hilo aparte para no bloquear el arranque
    del servidor (Render necesita que el puerto responda rápido)."""
    def _construir():
        try:
            indice.construir("data/normativa/resolucion_0631_2015.txt")
        except Exception as e:
            logger.error(f"No se pudo construir el índice RAG al arrancar: {e}")

    threading.Thread(target=_construir, daemon=True).start()


@app.get("/webhook")
def verificar_webhook(request: Request):
    """Handshake de verificación que exige Meta al configurar el webhook."""
    params = request.query_params
    if (params.get("hub.mode") == "subscribe"
            and params.get("hub.verify_token") == settings.WHATSAPP_VERIFY_TOKEN):
        return int(params.get("hub.challenge", 0))
    raise HTTPException(403, "Token de verificación inválido")


@app.post("/webhook")
async def recibir(request: Request, db: Session = Depends(get_db)):
    cuerpo = await request.body()
    try:
        payload = json.loads(cuerpo)
        cambios = payload["entry"][0]["changes"][0]["value"]
        mensajes = cambios.get("messages", [])
    except (KeyError, IndexError, json.JSONDecodeError):
        return {"status": "ignored"}

    for msg in mensajes:
        msg_id = msg.get("id")
        if msg_id and db.get(MensajeProcesado, msg_id):
            logger.info(f"Mensaje {msg_id} ya procesado; se ignora (reintento)")
            continue

        telefono = msg.get("from")
        try:
            if msg.get("type") == "text":
                pregunta = msg["text"]["body"]
                logger.info(f"Pregunta de {telefono}: {pregunta}")

                if not indice.listo:
                    enviar_texto(telefono,
                        "⏳ El asistente todavía está cargando la normativa. "
                        "Intenta de nuevo en un minuto.")
                else:
                    respuesta = responder_pregunta(pregunta)
                    enviar_texto(telefono, respuesta)

            if msg_id:
                db.add(MensajeProcesado(whatsapp_id=msg_id))
                db.commit()
        except Exception as e:
            logger.error(f"ERROR procesando mensaje: {e}")
            db.rollback()
            if telefono:
                try:
                    enviar_texto(telefono,
                        "⚠️ Hubo un problema técnico respondiendo tu pregunta. "
                        "Intenta de nuevo en unos minutos.")
                except Exception as e2:
                    logger.error(f"No se pudo notificar el error: {e2}")

    return {"status": "ok"}


@app.api_route("/", methods=["GET", "HEAD"])
def health():
    return {"status": "ok", "app": "Asistente Cumplimiento Ambiental",
             "indice_listo": indice.listo,
             "fragmentos_indexados": len(indice.fragmentos)}
