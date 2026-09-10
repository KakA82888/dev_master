"""数据库引擎与会话（SQLAlchemy 2.x）。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import APP_DB_PATH

engine = create_engine(
    f"sqlite:///{APP_DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401  确保表已注册

    Base.metadata.create_all(bind=engine)
