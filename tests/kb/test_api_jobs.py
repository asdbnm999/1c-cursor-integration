import pytest

from web.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_job_stream_not_found(client):
    res = client.get("/kb/api/jobs/nonexistent/stream")
    assert res.status_code == 200
    assert b"not found" in res.data or b"error" in res.data


def test_job_cancel_not_found(client):
    res = client.post("/kb/api/jobs/nonexistent/cancel")
    assert res.status_code == 404
    data = res.get_json()
    assert data["ok"] is False
