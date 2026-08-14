"""Cliente mínimo de la WhatsApp Cloud API: responder mensajes."""
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger("uvicorn.error")

GRAPH = "https://graph.facebook.com/v21.0"
ERRORES_TRANSITORIOS = (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)


def _con_reintentos(func, intentos: int = 3, espera_base: float = 1.5):
    for intento in range(1, intentos + 1):
        try:
            return func()
        except ERRORES_TRANSITORIOS as e:
            if intento == intentos:
                raise
            espera = espera_base * intento
            logger.warning(f"WhatsApp: intento {intento}/{intentos} falló ({type(e).__name__}); reintentando en {espera:.1f}s")
            time.sleep(espera)


def enviar_texto(telefono: str, texto: str) -> None:
    try:
        r = _con_reintentos(lambda: httpx.post(
            f"{GRAPH}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages",
            headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
            json={
                "messaging_product": "whatsapp",
                "to": telefono,
                "type": "text",
                "text": {"body": texto},
            },
            timeout=15,
        ))
        if r.status_code >= 400:
            logger.error(f"WHATSAPP SEND FALLÓ [{r.status_code}]: {r.text[:400]}")
        else:
            logger.info(f"WhatsApp send OK a {telefono}")
    except Exception as e:
        logger.error(f"WHATSAPP SEND EXCEPCIÓN: {e}")
