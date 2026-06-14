# Stock Research Hypothesis Cycle

Status date: 2026-06-14

The hypothesis loop is forward-only. Live hypotheses are created before the
outcome window is known, then evaluated after that window closes. Debug
backfills are allowed only as date-window and source-cutoff harnesses, and are
never training-eligible.

## Weekly Commands

Create the current live vintage:

```bash
python -m server.hypothesis_cycle create --vintage-date YYYY-MM-DD
```

Evaluate a closed live vintage with fixture market data:

```bash
python -m server.hypothesis_cycle evaluate \
  --vintage-date YYYY-MM-DD \
  --prices-json path/to/prices.json
```

Write a calibration summary from completed, training-eligible live outcomes:

```bash
python -m server.hypothesis_cycle calibrate
```

Run the doctor:

```bash
python -m server.stock_research_doctor --json
```

## Debug Backfills

Use debug backfills only to validate date-window logic and no-lookahead source
filters:

```bash
python -m server.hypothesis_cycle debug-backfill --vintage-date 2026-05-31 --horizon-days 7
python -m server.hypothesis_cycle debug-backfill --vintage-date 2026-06-07 --horizon-days 7
```

Expected windows:

| Debug vintage | Evaluation start | Evaluation end |
|---|---:|---:|
| 2026-05-31 | 2026-06-01 | 2026-06-07 |
| 2026-06-07 | 2026-06-08 | 2026-06-14 |

Debug rows remain `eligible_for_training: false`.

## Doctor Guardrails

The Stock Research doctor reports stable issue types for:

- `missing_current_live_hypothesis_vintage`
- `hypothesis_generated_after_window_start`
- `hypothesis_outcome_missing_after_window_close`
- `training_summary_includes_debug_rows`
- `hypothesis_source_cutoff_violation`
- `malformed_hypothesis_data`
