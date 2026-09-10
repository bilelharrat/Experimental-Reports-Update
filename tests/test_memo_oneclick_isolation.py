"""One-Click isolation guard: a pinned spine (studio card edits) may only
enter synthesis on the studio generate path. Exploration proved One-Click
cannot receive one today (fresh run_dir per report; pinned_spine_path set
only in _generate_from_studio; the editor store is never read by memo
workers) — this guard makes any future regression fail loudly instead of
silently producing a card-influenced One-Click memo."""
from __future__ import annotations

from pathlib import Path

import pytest

from server import memo_analysis


def test_assert_spine_pin_allowed():
    memo_analysis._assert_spine_pin_allowed(None, "auto")
    memo_analysis._assert_spine_pin_allowed(None, "studio")
    memo_analysis._assert_spine_pin_allowed(Path("/x/spine.json"), "studio")
    with pytest.raises(ValueError, match="studio-only"):
        memo_analysis._assert_spine_pin_allowed(Path("/x/spine.json"), "auto")
    with pytest.raises(ValueError, match="studio-only"):
        memo_analysis._assert_spine_pin_allowed(Path("/x/spine.json"), "")


def test_run_fast_synthesis_rejects_pin_without_studio_mode(tmp_path):
    # The guard is the first statement — dummy kwargs never get touched.
    with pytest.raises(ValueError, match="studio-only"):
        memo_analysis._run_fast_synthesis(
            run_dir=tmp_path,
            stream=None,
            company_name="X",
            company_slug="x",
            run_id="r",
            memo_paths={},
            research_dir=tmp_path,
            analysis_session_path=None,
            lessons_path=None,
            scope_check=None,
            warnings=[],
            pinned_spine_path=tmp_path / "spine.json",
        )
