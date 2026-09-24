"""Round 2, P1b: the agents' read fence (I15) and cancel-on-failure (I14).

No test here spawns the CLI: `_popen_claude` is faked, and the sandbox is
built against tmp repo/data roots so nothing reads the real data/.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import threading
import time

import pytest

from server import claude_runner


# ---- the read fence -----------------------------------------------------------


def _roots(tmp_path):
    repo = tmp_path / "repo"
    data = repo / "data"
    for name in ("server", "tests", "frontend", "scripts"):
        (repo / name).mkdir(parents=True)
    (repo / ".env").write_text("SECRET=1", encoding="utf-8")
    for name in ("uploads", "consoles", "settings", "memos", "research"):
        (data / name).mkdir(parents=True)
    (data / "companies.yaml").write_text("companies: []", encoding="utf-8")
    own_run = data / "memos" / "zainar-inc" / "2026-09-23__run"
    (own_run / "logs").mkdir(parents=True)
    (data / "memos" / "zainar-inc" / "2026-08-31__older").mkdir()
    (data / "memos" / "other-co" / "run").mkdir(parents=True)
    (data / "research" / "zainar-inc").mkdir()
    (data / "research" / "other-co").mkdir()
    return repo, data, own_run


def test_sandbox_rules_deny_everything_but_the_run_and_its_inputs(tmp_path):
    repo, data, own_run = _roots(tmp_path)
    research = data / "research" / "zainar-inc"
    rules = claude_runner.memo_agent_sandbox_rules(
        own_run, [research, data / "settings"], repo_root=repo, data_dir=data
    )
    # The CLI's absolute-path form: a double slash.
    assert f"Read(/{repo}/server/**)" in rules
    assert f"Read(/{repo}/tests/**)" in rules
    assert f"Read(/{repo}/frontend/**)" in rules
    assert f"Read(/{repo}/.env)" in rules and f"Read(/{repo}/.env.*)" in rules
    assert "Read(~/.ssh/**)" in rules
    assert f"Read(/{data}/uploads/**)" in rules
    assert f"Read(/{data}/consoles/**)" in rules
    # Other companies' memos, this company's other runs, other research.
    assert f"Read(/{data}/memos/other-co/**)" in rules
    assert f"Read(/{data}/memos/zainar-inc/2026-08-31__older/**)" in rules
    assert f"Read(/{data}/research/other-co/**)" in rules
    # Never the run, its company folder, its research, or a granted dir.
    joined = "\n".join(rules)
    assert str(own_run) not in joined
    assert f"{data}/memos/zainar-inc/**" not in joined
    assert f"{data}/research/zainar-inc/**" not in joined
    assert f"{data}/settings/**" not in joined
    assert f"{data}/memos/**" not in joined and f"{data}/research/**" not in joined
    assert all(r.startswith("Read(") for r in rules)
    assert len(rules) == len(set(rules))


def test_sandbox_file_is_valid_settings_json(tmp_path):
    repo, data, own_run = _roots(tmp_path)
    path = claude_runner.write_memo_agent_sandbox(
        own_run, [data / "research" / "zainar-inc"], repo_root=repo, data_dir=data
    )
    # One file per grant set under .claude/sandbox, never the auto-loaded
    # project settings name.
    assert path.parent == own_run / ".claude" / "sandbox"
    assert not (own_run / ".claude" / "settings.json").exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload["permissions"]["deny"], list)
    assert payload["permissions"]["deny"]
    assert str(data / "research" / "zainar-inc") in payload["_bsh_sandbox"]["allowed"]


def test_sandbox_never_raises(tmp_path, monkeypatch):
    # An unwritable run dir: no settings file, no exception.
    blocked = tmp_path / "file"
    blocked.write_text("x", encoding="utf-8")
    assert claude_runner.write_memo_agent_sandbox(blocked / "run", []) is None


class _FakeProc:
    def __init__(self, cmd, cwd, events=None):
        self.cmd = cmd
        self.pid = 4242
        self._bsh_spawn_cwd = cwd
        self.returncode = 0
        result = {
            "type": "result",
            "subtype": "success",
            "result": json.dumps({"answer": 1}),
            "total_cost_usd": 0.01,
            "duration_ms": 5,
            "usage": {},
        }
        lines = [json.dumps(e) for e in (events or [])] + [json.dumps(result)]
        self.stdout = io.StringIO("\n".join(lines) + "\n")
        self.stderr = io.StringIO("")

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0


def _flag(cmd, name):
    return cmd[cmd.index(name) + 1]


def test_the_funnel_passes_the_settings_file_and_drops_permission_roots(tmp_path, monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(
        claude_runner, "_popen_claude",
        lambda cmd, **kw: (seen.update(cmd=cmd, kwargs=kw) or _FakeProc(cmd, kw.get("cwd"))),
    )
    data = tmp_path / "data"
    run_dir = data / "memos" / "acme" / "run"
    (run_dir / "logs").mkdir(parents=True)
    research = data / "research" / "acme"
    research.mkdir(parents=True)
    (data / "settings").mkdir()
    result, error = claude_runner._run_memo_local_json_artifact_inner(
        prompt="p",
        schema={"type": "object"},
        run_dir=run_dir,
        progress=None,
        progress_message="m",
        timeout_label="t",
        timeout_sec=10,
        add_dirs=[data / "settings", data, research],
    )
    assert error is None and result["answer"] == 1
    cmd = seen["cmd"]
    settings = _flag(cmd, "--settings")
    assert Path(settings).parent == run_dir / ".claude" / "sandbox"
    payload = json.loads(Path(settings).read_text(encoding="utf-8"))
    assert any(rule.startswith("Read(//") for rule in payload["permissions"]["deny"])
    add_dirs = [cmd[i + 1] for i, part in enumerate(cmd) if part == "--add-dir"]
    # The run itself, the settings folder and the research folder — never
    # data/ (an ancestor of the run: a permission root, not an input).
    assert add_dirs == [str(run_dir), str(data / "settings"), str(research)]


def test_the_ic_memo_agent_runs_without_bash_and_with_the_fence(tmp_path, monkeypatch):
    seen: dict = {}

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        raise FileNotFoundError("stop here")

    monkeypatch.setattr(claude_runner, "_popen_claude", fake_popen)
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    run_dir = tmp_path / "data" / "memos" / "acme" / "run"
    (run_dir / "logs").mkdir(parents=True)
    settings = tmp_path / "data" / "settings" / "serena_background.md"
    settings.parent.mkdir(parents=True)
    settings.write_text("background", encoding="utf-8")
    companies = tmp_path / "data" / "companies.yaml"
    companies.write_text("- id: acme\n  name: Acme\n", encoding="utf-8")
    result = claude_runner.run_internal_diligence_memo(
        run_dir=run_dir,
        company_name="Acme",
        company_slug="acme",
        run_id="r1",
        settings_path=settings,
        companies_yaml_path=companies,
        memo_paths={"en": str(run_dir / "memo" / "en.docx")},
        internal_markdown_path=run_dir / "memo" / "ic.md",
    )
    assert result["ok"] is False
    cmd = seen["cmd"]
    assert _flag(cmd, "--tools") == claude_runner.MEMO_IC_MEMO_TOOLS
    assert "Bash" not in _flag(cmd, "--tools")
    assert _flag(cmd, "--allowedTools") == claude_runner.MEMO_IC_MEMO_TOOLS
    assert Path(_flag(cmd, "--settings")).parent == run_dir / ".claude" / "sandbox"
    # The legacy skill keeps its shell.
    assert "Bash" in claude_runner.MEMO_WRITER_TOOLS


def test_a_server_source_read_aborts_the_ic_memo_agent(tmp_path, monkeypatch):
    repo = claude_runner._repo_root()
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": f"{repo}/server/memo_analysis.py"}}
                ]
            },
        }
    ]
    terminated: list = []
    monkeypatch.setattr(
        claude_runner, "_popen_claude",
        lambda cmd, **kw: _FakeProc(cmd, kw.get("cwd"), events),
    )
    monkeypatch.setattr(
        claude_runner, "_terminate_process_group", lambda proc, **kw: terminated.append(proc)
    )
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    run_dir = tmp_path / "data" / "memos" / "acme" / "run"
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "memo").mkdir()
    settings = tmp_path / "data" / "settings" / "serena_background.md"
    settings.parent.mkdir(parents=True)
    settings.write_text("background", encoding="utf-8")
    companies = tmp_path / "data" / "companies.yaml"
    companies.write_text("- id: acme\n", encoding="utf-8")
    md = run_dir / "memo" / "ic.md"
    md.write_text("# would have been written", encoding="utf-8")
    result = claude_runner.run_internal_diligence_memo(
        run_dir=run_dir,
        company_name="Acme",
        company_slug="acme",
        run_id="r1",
        settings_path=settings,
        companies_yaml_path=companies,
        memo_paths={},
        internal_markdown_path=md,
    )
    assert result["ok"] is False
    assert result["error_code"] == claude_runner.IC_MEMO_BOUNDARY_ERROR_CODE == "boundary_violation"
    assert "server" in result["error"]
    assert result["boundary_hit"].startswith("Read: ")
    assert len(terminated) == 1


def test_boundary_hit_ignores_web_tools_and_other_paths(tmp_path):
    repo = claude_runner._repo_root()
    ok = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": f"{repo}/data/memos/x/analysis/a.md"}},
        {"type": "tool_use", "name": "WebFetch", "input": {"url": f"{repo}/server/"}},
        {"type": "text", "text": f"{repo}/server/ mentioned in prose"},
    ]}}
    assert claude_runner._tool_use_boundary_hit(ok) is None
    grep = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Grep", "input": {"pattern": "x", "path": f"{repo}/server"}},
    ]}}
    assert claude_runner._tool_use_boundary_hit(grep) is None  # no trailing slash: not the tree
    grep["message"]["content"][0]["input"]["path"] = f"{repo}/server/"
    assert claude_runner._tool_use_boundary_hit(grep) == f"Grep: {repo}/server/"
    assert claude_runner._tool_use_boundary_hit({"type": "result"}) is None


# ---- cancel on failure -----------------------------------------------------------


def _loc(en: str, zh: str = "") -> dict:
    return {"en": en, "zh": zh}


def _section(section_id: str) -> dict:
    return {"id": section_id, "blocks": [{"type": "paragraph", "text": _loc("Alpha.")}]}


def test_chaser_cancel_reaps_the_run_and_cancels_the_queue(tmp_path, monkeypatch):
    reaped: list[str] = []
    monkeypatch.setattr(
        claude_runner, "terminate_claude_procs_under", lambda run_dir: (reaped.append(run_dir) or 2)
    )
    started = threading.Event()
    release = threading.Event()
    ran: list[str] = []

    def slow_unit(*, unit_label, **kwargs):
        ran.append(unit_label)
        started.set()
        release.wait(timeout=5)
        unit = {"blocks": [{"type": "paragraph", "text": _loc("Alpha.", "阿尔法。")}]}
        unit["claude_cost_usd"] = 0.25
        unit["claude_duration_ms"] = 10
        return unit, None

    monkeypatch.setattr(claude_runner, "_run_bilingual_unit", slow_unit)
    events: list[tuple] = []

    class Stream:
        def emit(self, kind, **fields):
            events.append((kind, fields))

    chaser = claude_runner.BilingualChaser(
        run_dir=tmp_path, company_name="T", run_id="r", stream=Stream(), max_workers=1
    )
    chaser.on_section("executive_summary", _section("executive_summary"))
    chaser.on_section("risks", _section("risks"))  # queued behind the first
    assert started.wait(timeout=5)

    def _release_later():
        time.sleep(0.2)
        release.set()

    threading.Thread(target=_release_later, daemon=True).start()
    outcome = chaser.shutdown(cancel=True, wait_sec=5)
    assert chaser.cancelled
    assert reaped == [str(tmp_path)]
    assert outcome["reaped"] == 2
    assert outcome["cancelled"] == 1  # the queued unit never ran
    assert ran == ["section executive_summary (chase)"]
    # The unit that finished after the cancel is money the run must count.
    assert outcome["post_cancel_cost_usd"] == 0.25
    assert chaser.post_cancel_cost_usd == 0.25
    # The queued unit's row was closed, once.
    failed = [f for k, f in events if k == "thread_failed" and f.get("unit_id") == "risks"]
    assert len(failed) == 1 and "cancelled" in failed[0]["error"]
    # Nothing is accepted after the cancel.
    chaser.on_section("thesis_market", _section("thesis_market"))
    assert chaser.unit_count == 2


def test_chaser_plain_shutdown_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(
        claude_runner, "terminate_claude_procs_under",
        lambda run_dir: pytest.fail("a plain shutdown must not reap"),
    )
    chaser = claude_runner.BilingualChaser(run_dir=tmp_path, company_name="T", run_id="r")
    assert chaser.shutdown() == {"cancelled": 0, "reaped": 0, "post_cancel_cost_usd": 0.0}
    assert chaser.cancelled is False


def test_artifacts_cancel_reaps_and_counts_late_spend(tmp_path, monkeypatch):
    reaped: list[str] = []
    monkeypatch.setattr(
        claude_runner, "terminate_claude_procs_under", lambda run_dir: (reaped.append(run_dir) or 1)
    )
    started = threading.Event()
    release = threading.Event()

    def slow_artifacts(**kwargs):
        started.set()
        release.wait(timeout=5)
        return {"analysis_artifacts": {"a": "b"}, "claude_cost_usd": 0.4}, None

    monkeypatch.setattr(claude_runner, "run_memo_fast_english_artifacts", slow_artifacts)
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    artifacts = claude_runner.AsyncArtifacts(run_dir=run_dir, company_name="T")
    artifacts.start(common_context="ctx", add_dirs=[])
    assert started.wait(timeout=5)
    threading.Thread(target=lambda: (time.sleep(0.2), release.set()), daemon=True).start()
    outcome = artifacts.shutdown(cancel=True, wait_sec=5)
    assert reaped == [str(run_dir)]
    assert outcome == {"cancelled": 0, "reaped": 1, "post_cancel_cost_usd": 0.4}
    assert artifacts.cancelled and artifacts.post_cancel_cost_usd == 0.4


def test_artifacts_cancel_before_start_cancels_the_future(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_runner, "terminate_claude_procs_under", lambda run_dir: 0)
    artifacts = claude_runner.AsyncArtifacts(run_dir=tmp_path, company_name="T")
    assert artifacts.shutdown(cancel=True) == {"cancelled": 0, "reaped": 0, "post_cancel_cost_usd": 0.0}
    assert artifacts.shutdown() == {"cancelled": 0, "reaped": 0, "post_cancel_cost_usd": 0.0}


def test_the_runs_own_research_folder_stays_readable(tmp_path):
    # Live runs read research/<company>/sources 50+ times; most spawns grant
    # only the run folder, so the fence must keep the company's own
    # research folder open while still closing every other company's.
    repo = tmp_path / "repo"
    data = repo / "data"
    run = data / "memos" / "zainar-inc" / "2026-09-23__000000__zainar-inc__memo-run"
    run.mkdir(parents=True)
    (data / "memos" / "zainar-inc" / "2026-09-22__000000__zainar-inc__memo-run").mkdir()
    (data / "research" / "zainar-inc" / "sources").mkdir(parents=True)
    (data / "research" / "other-co").mkdir(parents=True)
    (data / "deal_pipeline").mkdir(parents=True)
    rules = claude_runner.memo_agent_sandbox_rules(run, [run], repo_root=repo, data_dir=data)
    joined = "\n".join(rules)
    assert "research/zainar-inc" not in joined
    assert "research/other-co" in joined
    assert "deal_pipeline" in joined
    assert "2026-09-22__000000__zainar-inc__memo-run" in joined
    assert "/server/**" in joined



def test_concurrent_spawns_with_different_grants_keep_their_own_fence(tmp_path):
    # Live 2026-09-23: one shared settings file was overwritten by a
    # concurrent spawn, and the IC memo agent lost its settings-folder grant.
    repo, data, own_run = _roots(tmp_path)
    (data / "settings").mkdir(parents=True, exist_ok=True)
    ic = claude_runner.write_memo_agent_sandbox(
        own_run, [data / "settings"], repo_root=repo, data_dir=data
    )
    writer = claude_runner.write_memo_agent_sandbox(own_run, [], repo_root=repo, data_dir=data)
    assert ic != writer
    ic_rules = json.loads(ic.read_text(encoding="utf-8"))["permissions"]["deny"]
    writer_rules = json.loads(writer.read_text(encoding="utf-8"))["permissions"]["deny"]
    assert not any("/settings/" in rule for rule in ic_rules)
    assert any("/settings/" in rule for rule in writer_rules)


def test_a_legacy_shared_settings_file_is_removed(tmp_path):
    repo, data, own_run = _roots(tmp_path)
    legacy = own_run / ".claude" / "settings.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text('{"_bsh_sandbox": {}, "permissions": {"deny": []}}', encoding="utf-8")
    claude_runner.write_memo_agent_sandbox(own_run, [], repo_root=repo, data_dir=data)
    assert not legacy.exists()
