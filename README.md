# 🤖 Asistente de Emisiones Fugitivas (RAG vía WhatsApp)

Bot de WhatsApp que responde preguntas técnicas sobre detección y reparación de
emisiones fugitivas con cámara OGI (Optical Gas Imaging), citando siempre el
artículo/sección exacta de la normativa que sustenta la respuesta — usando
**RAG (Retrieval-Augmented Generation)**, no un LLM respondiendo "de memoria".

## Por qué existe

Los proyectos de portafolio típicos que "llaman a la API de Claude" demuestran
integración, pero no necesariamente comprensión de cómo construir un sistema
de recuperación de información real. Este proyecto sí:

- **Embeddings semánticos** (Gemini `text-embedding-004`) para indexar la
  normativa por significado, no por palabras clave.
- **Búsqueda por similitud coseno** en memoria (sin depender de un vector DB
  externo — suficiente para un corpus de este tamaño, con la arquitectura
  lista para escalar a pgvector/Pinecone si el corpus crece).
- **Generación aumentada**: Claude solo responde con base en los fragmentos
  recuperados, y se le instruye explícitamente a decir "no lo sé" si la
  normativa indexada no cubre la pregunta — para minimizar alucinaciones en
  un dominio donde una respuesta incorrecta tiene consecuencias reales.

## Arquitectura

```
WhatsApp → FastAPI webhook → (dedup por ID de mensaje)
                            → embedding de la pregunta (Gemini)
                            → búsqueda semántica en el índice (numpy, coseno)
                            → top-3 fragmentos relevantes + pregunta → Claude
                            → respuesta con cita del artículo exacto → WhatsApp
```

## Base de conocimiento actual

**40 CFR Part 60, Subpart OOOOb — §60.5397b** (EPA, Estados Unidos): frecuencias
de monitoreo OGI/AVO/Método 21 según tipo de instalación (pozos, CPF, estaciones
de compresión), plazos de reparación de fugas, especificaciones técnicas del
equipo OGI, y umbral de eventos "super-emisor".

> Colombia no cuenta con una normativa pública tan detallada y técnica sobre
> frecuencias OGI y plazos de reparación como la EPA de Estados Unidos, así
> que esta regla se usa aquí como **referencia técnica internacional de
> buenas prácticas**, no como ley vigente en Colombia — el asistente lo aclara
> en cada respuesta. Los manuales/procedimientos internos de una empresa
> específica (ej. GOP-F-006) no deben subirse a un repositorio público; la
> arquitectura es la misma si se quisiera indexar documentación interna en un
> despliegue privado.

## Stack

FastAPI · Gemini Embeddings API · Claude (Anthropic) · WhatsApp Cloud API ·
SQLAlchemy + PostgreSQL (deduplicación de mensajes) · Docker · Render

## Variables de entorno

| Variable | Descripción |
|---|---|
| `WHATSAPP_TOKEN` | Token de acceso de WhatsApp Cloud API |
| `WHATSAPP_PHONE_NUMBER_ID` | ID del número de WhatsApp Business |
| `WHATSAPP_VERIFY_TOKEN` | Token propio para el handshake de verificación de Meta |
| `ANTHROPIC_API_KEY` | Clave de la API de Claude |
| `GEMINI_API_KEY` | Clave de la API de Gemini (para embeddings) |
| `DATABASE_URL` | Postgres para deduplicación (opcional; usa SQLite si no se define) |

## Extender la base de conocimiento

Agregar un documento nuevo: colocar el `.txt` en `data/normativa/`, separando
artículos/secciones con `===`, y apuntar `indice.construir(...)` al archivo
nuevo (o iterar sobre varios archivos) en `app/main.py`.

---

⚠️ **Aviso**: este asistente no sustituye asesoría legal o ambiental
profesional, ni los procedimientos internos oficiales de ninguna empresa.
