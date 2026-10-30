import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
import app.models  # noqa: F401  — registra todas las tablas en Base.metadata


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
