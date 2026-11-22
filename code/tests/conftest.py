import httpx
import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network call in test")

    monkeypatch.setattr(httpx, "get", boom)
    monkeypatch.setattr(httpx, "post", boom)


@pytest.fixture(autouse=True)
def infra_from_file_only(monkeypatch):
    """Kanał infra w testach tylko z pliku (tryb `auto` pytałby DNS o nowe domeny); testy innych trybów ustawiają go same."""
    monkeypatch.setenv("EMBSIM_INFRA", "cache")
