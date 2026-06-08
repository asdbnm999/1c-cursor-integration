import pytest

from web.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_wizard_preview(client, xml_export_tree):
    res = client.post(
        "/kb/api/wizard/preview",
        json={"root": str(xml_export_tree), "include_forms": False},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["detected_format"] == "xml_export"
    assert data["preview"]["total_indexable"] >= 1


def test_wizard_embeddings_check_local(client):
    res = client.post(
        "/kb/api/wizard/embeddings/check",
        json={"provider": "local", "device": "cpu"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert "message" in data


def test_wizard_embeddings_check_openai_missing(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    res = client.post(
        "/kb/api/wizard/embeddings/check",
        json={"provider": "openai"},
    )
    data = res.get_json()
    assert data["ok"] is False
