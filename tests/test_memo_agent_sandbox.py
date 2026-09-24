"""The memo agents' sandbox and the subprocess funnel's mechanics.

- ``--tools`` carries exactly the allow-list (Read,Grep,Glob,WebSearch,
  WebFetch; handoff workers add Write), matching the owner's verified
  bcf2409 grant; ``BSH_MEMO_AGENT_TOOLS`` overrides.
- The writer agents (legacy skill, resume, IC memo, Buffett, Hormuz) and the
  document readers get ``--tools`` pinned to their own allow-list.
- Agents get the server's environment minus secrets they do not need, and a
  TMPDIR inside the run.
- A Gemini stage gets the shared run context Claude gets through
  --append-system-prompt.
- A SIGTERM exit nobody asked for says so; a provider limit is remembered.
- After a run, tool uses that reached outside its inputs become a warning.
"""
from __future__ import annotations

import io
import json

import pytest

from server import claude_runner, job_progress, memo_analysis, memo_engine, memo_prep, provider_limits


class _FakeProc:
    def __init__(self, cmd, cwd):
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
        self.stdout = io.StringIO(json.dumps(result) + "\n")
        self.stderr = io.StringIO("")

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def capture(monkeypatch):
    seen: dict = {}

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return _FakeProc(cmd, kwargs.get("cwd"))

    monkeypatch.setattr(claude_runner, "_popen_claude", fake_popen)
    monkeypatch.delenv("BSH_MEMO_AGENT_TOOLS", raising=False)
    return seen


def _run_inner(tmp_path, **extra):
    return claude_runner._run_memo_local_json_artifact_inner(
        prompt="p",
        schema={"type": "object"},
        run_dir=tmp_path / "run",
        progress=None,
        progress_message="m",
        timeout_label="t",
        timeout_sec=10,
        **extra,
    )


def _flag(cmd, name):
    return cmd[cmd.index(name) + 1]


# ---- the tool grant ---------------------------------------------------------------


def test_agents_get_no_bash_by_default(tmp_path, capture):
    data, error = _run_inner(tmp_path)
    assert error is None and data["answer"] == 1
    cmd = capture["cmd"]
    tools = _flag(cmd, "--tools")
    assert tools == claude_runner.MEMO_AGENT_TOOLS_DEFAULT == "Read,Grep,Glob,WebSearch,WebFetch"
    assert "Bash" not in tools
    assert _flag(cmd, "--allowedTools") == tools
    # StructuredOutput rides --json-schema, which stays.
    assert "--json-schema" in cmd


def test_agent_tools_override_and_handoff_grant(tmp_path, capture, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_AGENT_TOOLS", " Read, Bash ,Grep ")
    assert claude_runner.memo_agent_tools() == "Read,Bash,Grep"
    _run_inner(tmp_path)
    assert _flag(capture["cmd"], "--tools") == "Read,Bash,Grep"
    monkeypatch.setenv("BSH_MEMO_AGENT_TOOLS", " , ")
    assert claude_runner.memo_agent_tools() == claude_runner.MEMO_AGENT_TOOLS_DEFAULT
    assert claude_runner._MEMO_SECTION_HANDOFF_TOOLS == "Read,Write,Grep,Glob,WebSearch,WebFetch"


def test_explicit_tool_free_call_stays_tool_free(tmp_path, capture):
    _run_inner(tmp_path, allowed_tools="", tools="")
    assert _flag(capture["cmd"], "--tools") == ""


def _writer_kwargs(tmp_path):
    run_dir = tmp_path / "data" / "memos" / "acme" / "run"
    (run_dir / "logs").mkdir(parents=True)
    settings = tmp_path / "data" / "settings" / "serena_background.md"
    settings.parent.mkdir(parents=True)
    settings.write_text("background", encoding="utf-8")
    companies = tmp_path / "data" / "companies.yaml"
    companies.write_text("- id: acme\n  name: Acme\n", encoding="utf-8")
    return dict(
        run_dir=run_dir,
        company_name="Acme",
        company_slug="acme",
        run_id="r1",
        settings_path=settings,
        companies_yaml_path=companies,
        memo_paths={"en": str(run_dir / "memo" / "en.docx"), "zh": str(run_dir / "memo" / "zh.docx")},
    )


@pytest.mark.parametrize(
    "runner, extra",
    [
        (claude_runner.run_investment_memo, {}),
        (claude_runner.run_resume_memo_package, {}),
        ("internal", {}),
    ],
)
def test_writer_agents_get_their_allow_list_as_the_tool_set(
    tmp_path, monkeypatch, runner, extra
):
    seen: dict = {}

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        raise FileNotFoundError("stop here")

    monkeypatch.setattr(claude_runner, "_popen_claude", fake_popen)
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    kwargs = _writer_kwargs(tmp_path)
    if runner == "internal":
        runner = claude_runner.run_internal_diligence_memo
        extra = {"internal_markdown_path": kwargs["run_dir"] / "memo" / "ic.md"}
    result = runner(**kwargs, **extra)
    assert result["ok"] is False
    cmd = seen["cmd"]
    # The IC memo agent lost Bash on 2026-09-23 (it writes Markdown; the
    # server renders the DOCX); the legacy skill and resume keep it.
    expected = (
        claude_runner.MEMO_IC_MEMO_TOOLS
        if runner is claude_runner.run_internal_diligence_memo
        else claude_runner.MEMO_WRITER_TOOLS
    )
    assert _flag(cmd, "--tools") == _flag(cmd, "--allowedTools") == expected
    env = seen["kwargs"]["env"]
    assert env["TMPDIR"] == str(kwargs["run_dir"] / "logs" / "tmp")


def test_document_readers_keep_only_read_and_bash():
    import inspect

    for fn in (claude_runner.run_quick_summary, claude_runner.run_research_analysis):
        source = inspect.getsource(fn)
        assert '"--tools", "Read,Bash",' in source
        assert "env=memo_agent_env()" in source


# ---- the environment ----------------------------------------------------------------


def test_agent_env_drops_secrets_and_keeps_the_cli_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("BSH_APNS_KEY_ID", "k")
    monkeypatch.setenv("BSH_BOOTSTRAP_PASSWORD", "pw")
    monkeypatch.setenv("SOME_SERVICE_TOKEN", "t")
    monkeypatch.setenv("STRIPE_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "o")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws")
    monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
    env = claude_runner.memo_agent_env(tmp_path / "run")
    for dropped in (
        "GEMINI_API_KEY",
        "BSH_APNS_KEY_ID",
        "BSH_BOOTSTRAP_PASSWORD",
        "SOME_SERVICE_TOKEN",
        "STRIPE_SECRET",
        "AWS_SECRET_ACCESS_KEY",
    ):
        assert dropped not in env
    assert env["ANTHROPIC_API_KEY"] == "a"
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "o"
    assert "PATH" in env
    assert env["TMPDIR"] == str(tmp_path / "run" / "logs" / "tmp")
    assert (tmp_path / "run" / "logs" / "tmp").is_dir()
    # On Bedrock the CLI's AWS credentials are its own auth.
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    assert claude_runner.memo_agent_env(None)["AWS_SECRET_ACCESS_KEY"] == "aws"


def test_the_funnel_spawns_with_the_filtered_env(tmp_path, capture, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    _run_inner(tmp_path)
    env = capture["kwargs"]["env"]
    assert "GEMINI_API_KEY" not in env
    assert env["TMPDIR"].endswith("/run/logs/tmp")


# ---- Gemini gets the shared context -------------------------------------------------


def test_a_gemini_stage_gets_the_shared_run_context(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    memo_engine.register_run_engine(run_dir, "gemini")
    seen: dict = {}

    def fake_artifact(**kwargs):
        seen.update(kwargs)
        return {"answer": "from gemini"}, None

    monkeypatch.setattr(memo_engine, "run_artifact", fake_artifact)
    data, error = claude_runner._run_memo_local_json_artifact(
        prompt="THE STAGE PROMPT",
        schema={"type": "object"},
        run_dir=run_dir,
        progress=None,
        progress_message="m",
        timeout_label="t",
        timeout_sec=60,
        append_system_prompt="REGISTRY ENTRY AND PINNED FACTS",
    )
    assert error is None and data == {"answer": "from gemini"}
    prompt = seen["prompt"]
    assert prompt.index("REGISTRY ENTRY AND PINNED FACTS") < prompt.index("THE STAGE PROMPT")
    memo_engine.clear_run_engine(run_dir)


def test_a_claude_stage_keeps_the_append_system_prompt_path(tmp_path, capture, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    claude_runner._run_memo_local_json_artifact(
        prompt="THE STAGE PROMPT",
        schema={"type": "object"},
        run_dir=run_dir,
        progress=None,
        progress_message="m",
        timeout_label="t",
        timeout_sec=60,
        append_system_prompt="SHARED",
    )
    cmd = capture["cmd"]
    assert _flag(cmd, "-p") == "THE STAGE PROMPT"
    assert _flag(cmd, "--append-system-prompt") == "SHARED"


# ---- SIGTERM and provider limits ------------------------------------------------------


def _funnel_with_inner_error(tmp_path, monkeypatch, error):
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact_inner", lambda **_kw: (None, error)
    )
    return run_dir, claude_runner._run_memo_local_json_artifact(
        prompt="p",
        schema={"type": "object"},
        run_dir=run_dir,
        progress=None,
        progress_message="m",
        timeout_label="t",
        timeout_sec=60,
    )


def test_an_unrequested_sigterm_says_so(tmp_path, monkeypatch):
    run_dir, (data, error) = _funnel_with_inner_error(tmp_path, monkeypatch, "claude exited 143")
    assert data is None
    assert error.startswith("killed by SIGTERM (not a cancel)")
    claude_runner.reset_run_dir_state(str(run_dir))


def test_a_cancelled_run_keeps_its_own_exit(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    claude_runner.mark_run_dir_cancelled(str(run_dir))
    try:
        assert claude_runner._explain_sigterm_exit("claude exited 143", run_dir) == "claude exited 143"
    finally:
        claude_runner.reset_run_dir_state(str(run_dir))
    assert claude_runner._explain_sigterm_exit("claude exited 1", run_dir) == "claude exited 1"


def test_a_provider_limit_is_remembered_for_the_preflight(tmp_path, monkeypatch):
    run_dir, (data, error) = _funnel_with_inner_error(
        tmp_path, monkeypatch, "Claude AI usage limit reached|resets 3pm"
    )
    try:
        assert data is None
        limit = provider_limits.current_limit("claude")
        assert limit is not None
        assert "usage limit" in limit["reason"].lower()
    finally:
        claude_runner.reset_run_dir_state(str(run_dir))
        provider_limits.clear_provider_limit()


# ---- the boundary audit ---------------------------------------------------------------


def test_the_boundary_audit_flags_reads_outside_the_run(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setattr(memo_prep, "DATA_DIR", data_root)
    run_dir = data_root / "memos" / "acme" / "2026-09-22__101010__acme__memo-run"
    (run_dir / "logs").mkdir(parents=True)
    repo = tmp_path.resolve()
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    reads = [
        ("Read", json.dumps({"file_path": f"{repo}/server/memo_quality_lint.py"})),
        ("Grep", json.dumps({"pattern": "P0", "path": f"{repo}/tests/"})),
        ("Read", json.dumps({"file_path": f"{repo}/.env"})),
        ("Read", json.dumps({"file_path": f"{repo}/data/uploads/acme/deck.pdf"})),
        ("Read", json.dumps({"file_path": f"{repo}/data/memos/other/run/analysis/x.md"})),
        # Inside the run and research folders: fine.
        ("Read", json.dumps({"file_path": f"{repo}/{memo_prep._rel(run_dir)}/analysis/a.md"})),
        ("Read", json.dumps({"file_path": f"{repo}/data/research/acme/deck.md"})),
        ("WebFetch", "https://example.com/server/.env"),
    ]
    for tool, preview in reads:
        stream.emit("claude_action", action="tool_use", tool=tool, preview=preview)

    hits = memo_analysis._audit_agent_boundary(run_dir)
    kinds = [hit["kind"] for hit in hits]
    assert kinds == ["server_source", "tests", "env_file", "uploads", "other_memo_run"]

    warnings = memo_analysis._RunWarnings()
    memo_analysis._boundary_warning(run_dir, warnings)
    assert warnings.en and "outside the run's inputs" in warnings.en[0]
    assert warnings.items[0]["gate"] == "boundary"
    assert (run_dir / "logs" / "boundary_audit.md").exists()


def test_a_quoted_path_to_the_runs_own_folder_is_not_another_run(tmp_path, monkeypatch):
    """ZaiNar 2026-09-23: a Bash preview is JSON, so `cd "<run folder>"`
    arrives with the path ending in a backslash-escaped quote, and the
    run's own folder was reported as another memo run's files."""
    data_root = tmp_path / "data"
    monkeypatch.setattr(memo_prep, "DATA_DIR", data_root)
    run_dir = data_root / "memos" / "acme" / "2026-09-22__101010__acme__memo-run"
    (run_dir / "logs").mkdir(parents=True)
    own = f"{tmp_path.resolve()}/{memo_prep._rel(run_dir)}"
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    stream.emit("claude_action", action="tool_use", tool="Bash", preview=json.dumps({"command": f'cd "{own}" && ls'}))
    assert memo_analysis._audit_agent_boundary(run_dir) == []
    # A sibling run (the same stem plus a suffix) quoted the same way still counts.
    sibling = own + "__2"
    stream.emit("claude_action", action="tool_use", tool="Bash", preview=json.dumps({"command": f'ls "{sibling}"'}))
    assert [hit["kind"] for hit in memo_analysis._audit_agent_boundary(run_dir)] == ["other_memo_run"]


def test_a_clean_run_has_no_boundary_warning(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setattr(memo_prep, "DATA_DIR", data_root)
    run_dir = data_root / "memos" / "acme" / "run"
    (run_dir / "logs").mkdir(parents=True)
    job_progress.ProgressLog(memo_prep.stream_path(run_dir)).emit(
        "claude_action", action="tool_use", tool="Read", preview='{"file_path": "x.md"}'
    )
    warnings = memo_analysis._RunWarnings()
    memo_analysis._boundary_warning(run_dir, warnings)
    assert not warnings
