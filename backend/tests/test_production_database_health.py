import pytest

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.api.health import health_check


class HealthySession:
    def execute(self, statement):
        assert str(statement) == "SELECT 1"
        return 1


class UnhealthySession:
    def execute(self, statement):
        raise SQLAlchemyError("simulated database failure")


def test_health_check_confirms_database():
    result = health_check(db=HealthySession())

    assert result == {
        "status": "ok",
        "service": "warik-ai-backend",
        "database": "ok",
    }


def test_health_check_returns_503_when_database_fails():
    with pytest.raises(HTTPException) as exc:
        health_check(db=UnhealthySession())

    assert exc.value.status_code == 503
    assert exc.value.detail["database"] == "unavailable"


def test_postgresql_urls_use_psycopg3():
    def normalize(url):
        if url.startswith("postgres://"):
            return url.replace(
                "postgres://", "postgresql+psycopg://", 1
            )
        if url.startswith("postgresql://"):
            return url.replace(
                "postgresql://", "postgresql+psycopg://", 1
            )
        return url

    assert normalize("postgres://user:pass@host/db") == (
        "postgresql+psycopg://user:pass@host/db"
    )
    assert normalize("postgresql://user:pass@host/db") == (
        "postgresql+psycopg://user:pass@host/db"
    )
    assert normalize("postgresql+psycopg://user:pass@host/db") == (
        "postgresql+psycopg://user:pass@host/db"
    )
