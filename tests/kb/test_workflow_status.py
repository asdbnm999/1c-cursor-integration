from packages.kb.indexer.workflow_status import compute_workflow_status


def test_workflow_all_complete(monkeypatch):
    monkeypatch.setattr("packages.kb.indexer.workflow_status.image_exists", lambda _name: True)
    wf = compute_workflow_status(
        profile_name="demo",
        chunks=100,
        index_job={"status": "completed"},
        docker_running=True,
        cursor_mcp={"status": "connected"},
    )
    assert wf["all_complete"] is True
    assert wf["completed_count"] == 4


def test_workflow_partial(monkeypatch):
    monkeypatch.setattr("packages.kb.indexer.workflow_status.image_exists", lambda _name: True)
    wf = compute_workflow_status(
        profile_name="demo",
        chunks=100,
        index_job={"status": "completed"},
        docker_running=False,
        cursor_mcp={"status": "missing"},
    )
    assert wf["all_complete"] is False
    assert wf["steps"]["index"] is True
    assert wf["steps"]["docker_running"] is False


def test_workflow_index_running_not_complete(monkeypatch):
    monkeypatch.setattr("packages.kb.indexer.workflow_status.image_exists", lambda _name: True)
    wf = compute_workflow_status(
        profile_name="demo",
        chunks=50,
        index_job={"status": "running"},
        docker_running=True,
        cursor_mcp={"status": "connected"},
    )
    assert wf["steps"]["index"] is False
    assert wf["all_complete"] is False
