"""Tests del envío a Telegram (sin red)."""

import pytest

from jobscout import notifier


class Respuesta:
    def __init__(self, status_code: int, data: dict | None = None):
        self.status_code = status_code
        self.ok = status_code == 200
        self._data = data or {}
        self.text = ""

    def json(self):
        return self._data


@pytest.fixture
def esperas(monkeypatch):
    """Registra los time.sleep en vez de esperar de verdad."""
    registradas = []
    monkeypatch.setattr(notifier.time, "sleep", registradas.append)
    return registradas


def test_reintenta_tras_429(monkeypatch, esperas):
    respuestas = [Respuesta(429, {"parameters": {"retry_after": 3}}), Respuesta(200)]
    monkeypatch.setattr(notifier.requests, "post", lambda *a, **kw: respuestas.pop(0))

    notifier.TelegramNotifier("token", "chat").send("hola")

    assert respuestas == []
    assert 3 in esperas


def test_error_con_descripcion(monkeypatch, esperas):
    monkeypatch.setattr(
        notifier.requests,
        "post",
        lambda *a, **kw: Respuesta(400, {"description": "chat not found"}),
    )
    with pytest.raises(RuntimeError, match="chat not found"):
        notifier.TelegramNotifier("token", "chat").send("hola")


def test_pausa_entre_mensajes(monkeypatch, esperas):
    monkeypatch.setattr(notifier.requests, "post", lambda *a, **kw: Respuesta(200))
    n = notifier.TelegramNotifier("token", "chat")
    n.send("uno")
    n.send("dos")
    assert esperas and esperas[-1] > 1.0
