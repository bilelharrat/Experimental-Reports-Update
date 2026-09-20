"""The spine delivers its parts as files, and is validated here.

2026-09-16: a spine was rejected four times as unparseable at 33,330 /
31,264 / 28,240 / 27,850 bytes — the model shrinking its own answer and
still not fitting — costing 10.5 minutes and a package attempt. A spine
that DOES succeed measures 30,713 characters, so every one of them is a
good paragraph away from the same wall. Its parts are already separable:
`sources` is 12KB on its own and `calculations` 6KB.

Moving it off the structured-output channel loses the CLI's schema
enforcement (it caught an 89-character metric name against a cap of 80,
and a fourth highlight against a cap of 3, and made the model fix both),
so `_schema_errors` reproduces that here and routes each complaint to the
file that owns it.
"""
from __future__ import annotations

import json

import pytest

from server import claude_runner, memo_structure

V2 = memo_structure.load_structure("late", 2)


def _schema(structure=V2):
    return claude_runner.memo_fast_english_spine_schema(structure)


def _plan(run_dir, structure=V2):
    return claude_runner._spine_piece_plan(run_dir, _schema(structure))


def _spine_payload():
    return {
        "package_skeleton": {
            "schema_version": 1,
            "company": {"name": "Acme"},
            "run": {"run_id": "r1"},
            "sources": [
                {
                    "id": "S1",
                    "title": {"en": "Data room", "zh": ""},
                    "class": "company-reported",
                    "treatment": {"en": "Primary.", "zh": ""},
                    "as_of": "2026-05-01",
                }
            ],
        },
        "shared_facts": {
            "recommendation_sentence": "Recommendation: BSH commits $10M.",
            "stage": "late",
            "verdict": "Buy",
            "scorecard": {
                "total": 70,
                "dimensions": {
                    key: {
                        "score": 1,
                        "why": "because.",
                        "evidence": [
                            "Revenue, which measures scale, is $1B [S1]."
                        ],
                    }
                    for key in memo_structure.SCORECARD_DIMENSION_KEYS
                },
            },
            "fair_value_range": {
                "low": "$800M", "high": "$1.4B", "basis": "comps",
            },
            "entry": {
                "valuation": "$1B", "basis": "post", "holding_period": "4y",
            },
            "highlights": [
                {
                    "dimension": key,
                    "headline": "The case holds here.",
                    "evidence": [
                        "Revenue, which measures scale, is $1B [S1].",
                        "Customers, which measure breadth, number 400 [S1].",
                    ],
                }
                for key in ("moat", "industry_position", "market_size_growth")
            ],
            "calculations": [
                {
                    "id": "C1",
                    "label": "Base MOIC",
                    "inputs": [
                        {"name": "exit", "value": "$2B", "ref": "assumption"}
                    ],
                    "formula": "$2B / $1B = 2.0x",
                    "result": "2.0x",
                    "meaning": "The base case doubles the money.",
                }
            ],
            "key_metrics": [
                {"name": "Run-rate revenue", "value": "$65B", "as_of": "2026-07-01"}
            ],
            "scenarios": {
                name: {
                    "narrative": "One line.",
                    "exit_year": "2030",
                    "exit_revenue": "$5B",
                    "exit_multiple": "8x",
                    "exit_value": "$40B",
                    "moic": moic,
                    "irr": "25%",
                }
                for name, moic in (
                    ("bear", "0.50x"), ("base", "1.80x"), ("bull", "4.00x")
                )
            },
            "risks": [
                {
                    "summary": f"Risk {n} is a complete verdict sentence.",
                    "rating": f"{9 - n}/10",
                    "likelihood": "High",
                    "area": area,
                    "impact": "The base case returns 0.9x — a loss.",
                }
                for n, area in enumerate(
                    (
                        "valuation_exit",
                        "market",
                        "competition",
                        "concentration",
                    )
                )
            ],
        },
        "section_notes": {},
    }


def _write_pieces(run_dir, payload, structure=V2, skip=()):
    written = []
    for _stem, target, keys, _req, _what, path in _plan(run_dir, structure):
        if path.name in skip:
            continue
        bucket = payload.get(target, {}) if target else payload
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({k: bucket[k] for k in keys if k in bucket}),
            encoding="utf-8",
        )
        written.append(path.name)
    return written


# ---- the piece plan ---------------------------------------------------------


def test_every_part_of_the_spine_has_a_home():
    """No declared spine key may fall through the plan unnoticed."""
    import pathlib

    schema = _schema()
    planned = set()
    for _stem, target, keys, _req, _what, _path in claude_runner._spine_piece_plan(
        pathlib.Path("/tmp"), schema
    ):
        planned.update((target, key) for key in keys)
    for target in ("package_skeleton", "shared_facts"):
        for key in schema["properties"][target].get("properties") or {}:
            assert (target, key) in planned, f"{target}.{key} has no file"
    assert ("", "section_notes") in planned


def test_a_v1_spine_plans_fewer_parts(tmp_path):
    """v1 has no scorecard, highlights or calculations to write."""
    v1_stems = {e[0] for e in _plan(tmp_path, memo_structure.LATE)}
    v2_stems = {e[0] for e in _plan(tmp_path, V2)}
    assert "highlights" in v2_stems and "calculations" in v2_stems
    assert "highlights" not in v1_stems and "calculations" not in v1_stems
    # the free-form v1 envelope still gets its files
    assert {"envelope", "sources"} <= v1_stems


def test_files_are_numbered_in_writing_order(tmp_path):
    names = [e[5].name for e in _plan(tmp_path)]
    assert names == sorted(names)
    assert names[0].startswith("01_")


# ---- per-piece validation ---------------------------------------------------


def test_a_good_piece_passes(tmp_path):
    _write_pieces(tmp_path, _spine_payload())
    for stem, _t, keys, req, _w, path in _plan(tmp_path):
        assert claude_runner._spine_piece_error(path, stem, keys, req) is None


@pytest.mark.parametrize(
    "raw,needle",
    [
        (None, "was never written"),
        ("{oops", "not valid JSON"),
        ("[1,2]", "is not a JSON object"),
        ('{"sources": [], "risks": []}', "belong in another file"),
    ],
)
def test_unusable_pieces_are_named(tmp_path, raw, needle):
    entry = next(e for e in _plan(tmp_path) if e[0] == "sources")
    stem, _t, keys, req, _w, path = entry
    if raw is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw, encoding="utf-8")
    error = claude_runner._spine_piece_error(path, stem, keys, req)
    assert error and needle in error


def test_a_missing_required_key_is_named(tmp_path):
    entry = next(e for e in _plan(tmp_path) if e[0] == "sources")
    stem, _t, keys, req, _w, path = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    error = claude_runner._spine_piece_error(path, stem, keys, req)
    assert error and "is missing" in error and "sources" in error


# ---- assembly ---------------------------------------------------------------


def test_the_parts_reassemble_into_the_original_spine(tmp_path):
    payload = _spine_payload()
    _write_pieces(tmp_path, payload)
    spine = claude_runner._assemble_spine(_plan(tmp_path))
    assert spine["package_skeleton"] == payload["package_skeleton"]
    assert spine["shared_facts"] == payload["shared_facts"]


# ---- schema errors route to the file that owns them -------------------------


@pytest.mark.parametrize(
    "error,stem",
    [
        ("/shared_facts/key_metrics/1/name: must NOT have more than 80 "
         "characters (got 89)", "metrics"),
        ("/shared_facts/highlights: must NOT have more than 3 items (got 4)",
         "highlights"),
        ("/shared_facts/risks/0/rating: must match the pattern x", "risks"),
        ("/package_skeleton/sources/2/id: must be string (got int)", "sources"),
        ("/shared_facts/calculations/0/formula: must NOT have more than 200 "
         "characters (got 260)", "calculations"),
        ("root: must have required property 'shared_facts'", "verdict"),
    ],
)
def test_a_schema_error_is_routed_to_its_file(tmp_path, error, stem):
    plan = _plan(tmp_path)
    expected = next(e[5].name for e in plan if e[0] == stem)
    assert claude_runner._spine_piece_for_schema_error(plan, error) == expected


def test_an_unroutable_error_is_reported_not_guessed(tmp_path):
    plan = _plan(tmp_path)
    assert (
        claude_runner._spine_piece_for_schema_error(plan, "something odd")
        is None
    )


# ---- the whole path ---------------------------------------------------------


def _run(tmp_path, monkeypatch, fake):
    monkeypatch.setenv("BSH_MEMO_SPINE_HANDOFF", "1")
    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake
    )
    return claude_runner.run_memo_fast_english_spine(
        run_dir=tmp_path,
        company_name="Acme",
        common_context="ctx",
        add_dirs=[],
        structure=V2,
    )


def test_a_clean_spine_assembles_in_one_call(tmp_path, monkeypatch):
    calls = []

    def fake(**kw):
        calls.append(kw)
        _write_pieces(tmp_path, _spine_payload())
        return {"pieces": [], "claude_cost_usd": 1.0}, None

    spine, error = _run(tmp_path, monkeypatch, fake)
    assert error is None
    assert len(calls) == 1
    assert spine["shared_facts"]["recommendation_sentence"].startswith(
        "Recommendation:"
    )
    assert spine["claude_cost_usd"] == 1.0
    assert calls[0]["schema"] is claude_runner._MEMO_SPINE_MANIFEST_SCHEMA
    assert "Write" in calls[0]["allowed_tools"]


def test_the_prompt_forbids_measuring_with_shell(tmp_path, monkeypatch):
    calls = []

    def fake(**kw):
        calls.append(kw)
        _write_pieces(tmp_path, _spine_payload())
        return {"pieces": []}, None

    _run(tmp_path, monkeypatch, fake)
    prompt = calls[0]["prompt"]
    assert "Write each file ONCE" in prompt
    assert "`wc`, `awk`, `jq`" in prompt
    assert "33,330" in prompt  # it says why, with the evidence
    # the spine's own brief still travels with it
    assert "recommendation_sentence" in prompt


def test_only_the_missing_part_is_re_asked(tmp_path, monkeypatch):
    calls = []
    target = next(e[5].name for e in _plan(tmp_path) if e[0] == "risks")

    def fake(**kw):
        calls.append(kw)
        if len(calls) == 1:
            _write_pieces(tmp_path, _spine_payload(), skip=(target,))
        else:
            _write_pieces(tmp_path, _spine_payload())
        return {"pieces": []}, None

    spine, error = _run(tmp_path, monkeypatch, fake)
    assert error is None
    assert len(calls) == 2
    retry = calls[1]["prompt"]
    assert "## Rewrite ONE part of the spine" in retry
    assert target in retry
    assert "do not rewrite them" in retry
    assert spine["shared_facts"]["risks"]


def test_a_part_gives_up_after_three_retries(tmp_path, monkeypatch):
    target = next(e[5].name for e in _plan(tmp_path) if e[0] == "risks")
    calls = []

    def fake(**kw):
        calls.append(kw)
        _write_pieces(tmp_path, _spine_payload(), skip=(target,))
        return {"pieces": []}, None

    spine, error = _run(tmp_path, monkeypatch, fake)
    assert spine is None
    assert "still unusable after 3 retries" in error
    assert len(calls) == 1 + claude_runner.MEMO_SPINE_PIECE_MAX_RETRIES


def test_a_schema_violation_re_asks_only_that_part(tmp_path, monkeypatch):
    """The enforcement the CLI used to provide, kept."""
    calls = []
    metrics_file = next(e[5].name for e in _plan(tmp_path) if e[0] == "metrics")
    # read the cap from the schema: it moves when the report gets longer
    cap = _schema()["properties"]["shared_facts"]["properties"]["key_metrics"][
        "items"
    ]["properties"]["name"]["maxLength"]

    def fake(**kw):
        calls.append(kw)
        payload = _spine_payload()
        if len(calls) == 1:
            payload["shared_facts"]["key_metrics"][0]["name"] = "x" * (cap + 9)
        _write_pieces(tmp_path, payload)
        return {"pieces": []}, None

    spine, error = _run(tmp_path, monkeypatch, fake)
    assert error is None
    assert len(calls) == 2
    retry = calls[1]["prompt"]
    assert metrics_file in retry
    assert f"must NOT have more than {cap} characters" in retry
    assert len(spine["shared_facts"]["key_metrics"][0]["name"]) <= cap


def test_parts_on_disk_survive_a_failed_drafting_call(tmp_path, monkeypatch):
    target = next(e[5].name for e in _plan(tmp_path) if e[0] == "risks")
    calls = []

    def fake(**kw):
        calls.append(kw)
        if len(calls) == 1:
            _write_pieces(tmp_path, _spine_payload(), skip=(target,))
            return None, "the model never returned output matching the schema"
        _write_pieces(tmp_path, _spine_payload())
        return {"pieces": []}, None

    spine, error = _run(tmp_path, monkeypatch, fake)
    assert error is None
    assert len(calls) == 2
    assert spine["shared_facts"]["risks"]


def test_a_call_that_wrote_nothing_fails_without_retries(tmp_path, monkeypatch):
    calls = []

    def fake(**kw):
        calls.append(kw)
        return None, "run cancelled"

    spine, error = _run(tmp_path, monkeypatch, fake)
    assert spine is None
    assert error == "run cancelled"
    assert len(calls) == 1


def test_stale_parts_are_cleared_first(tmp_path, monkeypatch):
    stale = next(e[5] for e in _plan(tmp_path) if e[0] == "risks")
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text('{"risks": [{"summary": "stale"}]}', encoding="utf-8")

    def fake(**kw):
        assert not stale.exists(), "the last attempt's files must be cleared"
        _write_pieces(tmp_path, _spine_payload())
        return {"pieces": []}, None

    spine, error = _run(tmp_path, monkeypatch, fake)
    assert error is None
    assert spine["shared_facts"]["risks"][0]["summary"] != "stale"


def test_the_handoff_can_be_turned_off(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_SPINE_HANDOFF", "0")
    calls = []

    def fake(**kw):
        calls.append(kw)
        return _spine_payload(), None

    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", fake)
    spine, error = claude_runner.run_memo_fast_english_spine(
        run_dir=tmp_path,
        company_name="Acme",
        common_context="ctx",
        add_dirs=[],
        structure=V2,
    )
    assert error is None
    assert calls[0]["schema"] is not claude_runner._MEMO_SPINE_MANIFEST_SCHEMA
    assert "Return only the JSON matching the attached schema." in (
        calls[0]["prompt"]
    )


def test_null_for_an_optional_field_means_absent(tmp_path):
    """Live 2026-09-16: a spine wrote `decision_history_sentence: null`.

    That is what a writer naturally puts when the run has no decision
    history, and it cost a retry that would only have deleted the key.
    """
    payload = _spine_payload()
    payload["shared_facts"]["decision_history_sentence"] = None
    _write_pieces(tmp_path, payload)
    spine = claude_runner._assemble_spine(_plan(tmp_path))
    assert "decision_history_sentence" not in spine["shared_facts"]
    assert not claude_runner._schema_errors(spine, _schema())


def test_null_for_a_required_field_still_fails(tmp_path):
    payload = _spine_payload()
    payload["shared_facts"]["recommendation_sentence"] = None
    _write_pieces(tmp_path, payload)
    spine = claude_runner._assemble_spine(_plan(tmp_path))
    errors = claude_runner._schema_errors(spine, _schema())
    assert any("recommendation_sentence" in e for e in errors)


# ---- the limits the model is asked to respect -------------------------------
#
# 2026-09-17, the Figure AI run. Three separate pieces were re-asked for
# marginal overruns: key_metrics with 21 items against 20, entry.valuation
# with 115 characters against 40, and calculations[].inputs[].name with 132
# against 100. All three limits live in the spine schema, which under the
# handoff the model NEVER SEES — its reply is a receipt, so the only schema
# the CLI shows it is the manifest's. The contract even told it that "the
# schema limits in your instructions still apply" when its instructions
# carried none. Each overrun bought a fresh subprocess to correct a number
# nobody had given it.


def _contract(tmp_path, structure=V2):
    schema = _schema(structure)
    plan = claude_runner._spine_piece_plan(tmp_path, schema)
    return claude_runner._spine_handoff_contract(
        plan, tmp_path / "pieces", schema
    )


def test_the_contract_states_the_limits_that_were_overrun(tmp_path):
    contract = _contract(tmp_path)
    assert "key_metrics: at most 20 items" in contract
    assert "entry.valuation: at most 40 characters" in contract
    assert (
        "calculations[].inputs[].name: at most 100 characters" in contract
    )


def test_the_contract_no_longer_claims_the_limits_are_elsewhere(tmp_path):
    contract = _contract(tmp_path)
    assert "limits in your instructions still apply" not in contract
    assert "the ONLY place those numbers appear" in contract


def test_identical_siblings_collapse_to_one_line(tmp_path):
    """Nine scorecard dimensions declare the same four bounds. Printing
    each cost about forty lines of prompt repeating itself."""
    contract = _contract(tmp_path)
    assert "scorecard.dimensions.<each>.why: at most 180 characters" in (
        contract
    )
    assert "scorecard.dimensions.market_size_growth.why" not in contract
    # nine dimensions collapsed to one line, so the only other 180 is
    # key_metrics[].name
    assert contract.count("<each>.why: at most 180") == 1
    assert contract.count("scorecard.dimensions.") == 5


def test_the_limits_are_read_from_the_schema_not_typed_in(tmp_path):
    """The whole point: one definition. Move the cap and the sentence the
    model reads moves with it."""
    schema = _schema()
    facts = schema["properties"]["shared_facts"]["properties"]
    facts["entry"]["properties"]["valuation"]["maxLength"] = 41
    facts["key_metrics"]["maxItems"] = 21
    plan = claude_runner._spine_piece_plan(tmp_path, schema)
    contract = claude_runner._spine_handoff_contract(
        plan, tmp_path / "pieces", schema
    )
    assert "entry.valuation: at most 41 characters" in contract
    assert "key_metrics: at most 21 items" in contract


def test_an_exact_count_reads_as_exact(tmp_path):
    contract = _contract(tmp_path)
    assert "highlights: exactly 3 items" in contract
    assert "3-3 items" not in contract


def test_enums_are_spelled_out(tmp_path):
    contract = _contract(tmp_path)
    assert "verdict: one of Strong Buy/Buy/Watch/Pass" in contract
    assert "risks[].likelihood: one of High/Medium/Low" in contract


def test_the_contract_stays_small_enough_to_prepend(tmp_path):
    """It rides in front of the spine body on every run, so it has to earn
    its tokens: the limits must not cost more than the instructions."""
    assert len(_contract(tmp_path)) < 8000


def test_a_v1_spine_only_states_the_limits_it_has(tmp_path):
    contract = _contract(tmp_path, memo_structure.LATE)
    assert "05_highlights.json" not in contract
    assert "07_calculations.json" not in contract
    assert "calculations[].inputs" not in contract
    # the parts v1 does have still carry their limits
    assert "04_metrics.json" in contract
    assert "key_metrics: at most" in contract
