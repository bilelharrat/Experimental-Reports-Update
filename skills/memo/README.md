# Memo report prompts (skills/memo)

This folder holds every editorial prompt the investment-memo agents run.
The English files are what the agents read at run time; the Chinese
twins under `zh/` are the editing surface for the Chinese team.

```
skills/memo/
  voice_contract.md        how the memo speaks (LP co-invest register, verdict-first)
  structure_addendum.md    structure-v2 rules: data honesty, citations, charts,
                           explanatory register, "teach, don't assert"
  risk_card_v2.md          the eight-row risk card (full reports)
  risk_card_compact.md     the bullet risk register (compact reports)
  passes.md                the Phase 2 research passes: id, label, artifact,
                           focus text — file order is dispatch order
  structures/              stage profiles: late_v2 / late_compact / growth /
                           early (+ late v1, which has no zh twin) and
                           components.yaml;
                           each `## section:` block's prose is that section's
                           contract, the yaml fence its metadata
  types/                   company-type lenses: ai_foundation_model, ai_infra,
                           ai_application, ai_video_short_drama, robotics,
                           other — front matter carries optional scorecard
                           weight overlays and per-pass research focus; the
                           body is the Phase 3 analysis lens
  buffett.md               the Buffett-method memo skill (BSH Research's owner's
                           analysis, one Claude run; not part of the late-stage passes)
  zh_style.md              the Chinese style guide + glossary (| English | 中文 |
                           Avoid |) every prompt that writes memo Chinese carries
  jurisdictions/           research overlays by jurisdiction (cn.md: Chinese
                           searches per pass), added to the passes' shared
                           context when the run detects that jurisdiction
  zh/                      Chinese twins, same paths, same headings
```

## How the pieces reach the agents

- Phase 1 classifies the company type (registry `vertical`, else a
  tool-free classifier) and the stage profile.
- Phase 2: every pass in `passes.md` runs as its own agent with its focus
  text plus the company type's `research_focus` for that pass. The
  `## Rules for every pass` block of `passes.md` (and a jurisdiction
  overlay, when one applies) rides the passes' shared context; the notes
  above that block reach no agent.
- Phase 3: the spine and every section worker share one cached context =
  `voice_contract.md` + the rules block of `passes.md` +
  `structure_addendum.md` + the type lens; each section worker also gets
  its own `## section:` contract from the stage profile, and the risk
  section gets its risk-card file.
- Chinese: every translation call (and the resume, full-skill and IC memo
  prompts) carries `zh_style.md` after the fixed number conventions.

## Editing workflow (中文说明见 zh/README.md)

1. The Chinese team edits the twin under `zh/` — prose only; the yaml
   fences are technical fields and are copied verbatim.
2. The owner asks Claude to "sync zh → en": the change is ported into the
   English file (the agents read English only), the twin is re-stamped,
   and the gates run.
3. `uv run python scripts/skills_sync.py --check` fails when an English
   file changed without its twin being re-stamped (`en_sha256` in the
   twin's front matter); `--stamp` re-stamps after a sync. The same check
   runs in the test suite.

Never edit the Python constants that load these files (`memo_prompts.
load_prompt(...)` lines) — edit the file.
