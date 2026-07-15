import json
from datetime import datetime, timedelta, timezone

from server import api, cache, files_store


class FakeThread:
    started: list["FakeThread"] = []

    def __init__(self, *, target, args=(), name=None, daemon=None):
        self.target = target
        self.args = args
        self.name = name
        self.daemon = daemon

    def start(self):
        self.started.append(self)


def _write_search_progress(path, *, query: str, seconds_old: int):
    ts = (
        datetime.now(timezone.utc) - timedelta(seconds=seconds_old)
    ).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "type": "job_init",
            "ts": ts,
            "kind": "search",
            "title": f'Searching "{query}"',
            "subtitle": "Company deep search",
            "query": query,
        },
        {
            "type": "stage",
            "ts": ts,
            "stage": "searching",
            "message": "Searching the web",
        },
    ]
    path.write_text(
        "".join(json.dumps(line) + "\n" for line in lines),
        encoding="utf-8",
    )


def test_company_search_start_supersedes_stale_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(files_store, "UPLOADS_ROOT", tmp_path / "uploads")
    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_path / "cache")
    FakeThread.started = []
    monkeypatch.setattr(api.threading, "Thread", FakeThread)

    query = "zainar"
    job_id = api._search_job_id(query)
    path = api._search_progress_path(job_id)
    _write_search_progress(
        path,
        query=query,
        seconds_old=api.SEARCH_JOB_MAX_IDLE_SECONDS + 1,
    )

    result = api.post_companies_search_start(request=_admin_request(), q=query, refresh=False)

    assert result["status"] == "queued"
    assert result["job_id"] == job_id
    assert not path.exists()
    assert len(FakeThread.started) == 1
    assert FakeThread.started[0].args == (job_id, query, False)


def test_company_search_start_attaches_to_recent_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(files_store, "UPLOADS_ROOT", tmp_path / "uploads")
    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_path / "cache")
    FakeThread.started = []
    monkeypatch.setattr(api.threading, "Thread", FakeThread)

    query = "zainar recent"
    job_id = api._search_job_id(query)
    path = api._search_progress_path(job_id)
    _write_search_progress(path, query=query, seconds_old=1)

    result = api.post_companies_search_start(request=_admin_request(), q=query, refresh=False)

    assert result["status"] == "already_running"
    assert result["job_id"] == job_id
    assert path.exists()
    assert FakeThread.started == []


def _admin_request():
    """Stub Request for calling gated handlers as plain functions:
    resolves to the anon-dev admin role in _caller_role."""
    from types import SimpleNamespace

    return SimpleNamespace(
        state=SimpleNamespace(auth_kind="anon_dev", session_email=None),
        cookies={},
        headers={},
    )
