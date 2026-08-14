from datetime import datetime, timezone

from sqlalchemy import DateTime, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import settings


def utcnow():
    return datetime.now(timezone.utc)


engine = create_engine(
    settings.db_url,
    connect_args={"check_same_thread": False} if settings.db_url.startswith("sqlite") else {},
    pool_pre_ping=True,
    pool_recycle=280,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


class MensajeProcesado(Base):
    __tablename__ = "mensajes_procesados"
    whatsapp_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    procesado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
