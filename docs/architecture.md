# BSH Research Center — Two-feature architecture

There are **two independent AI features** in the system. They share no
code paths, no run folders, no inputs. They do not invoke each other.

| | Document Library | Investment Memo |
|---|---|---|
| **Whose data** | The user's | Serena's |
| **Where files live** | `data/uploads/<slug>/` | `data/settings/serena_background.md` + `data/companies.yaml` record + optional `data/research/<slug>/` and approved Memo Studio packets |
| **User-facing surface** | Per-file Sparkle button inside the Library | "Generate Report → Investment Memo (Late-Stage)" panel |
| **What it produces** | A structured per-document summary (bilingual exec summary, sections, key points) saved onto the file's record | Two `.docx` files (English + Simplified Chinese) saved into a versioned run folder under `data/memos/<slug>/<run_id>__<slug>__memo-run/memo/` |
| **Backend module** | `server/deck_summary.py` + the document-summary endpoints in `server/api.py` | `server/memo_prep.py` + `server/memo_analysis.py` + the memo endpoints in `server/api.py` |
| **Runs Claude how** | One subprocess per uploaded file, page-by-page Read (configurable: granular or 8-page batch) | Default fast path runs eight narrow analysis subprocesses in parallel, then English package and Chinese package subprocesses. `BSH_MEMO_FAST_PIPELINE=0` restores the legacy one-subprocess Serena skill run. |

## Hard rules

1. **The memo skill never reads from `data/uploads/`.** The Document
   Library is the user's storage. The memo skill is Serena's flow.
   They are not the same library.

2. **The Sparkle button never produces inputs for the memo.** Sparkling
   a document and then generating a memo are two independent decisions.

3. **`memo_prep.py` does not stage any files into the run folder.** It
   creates the versioned run folder and a manifest, nothing else.

4. **Python owns orchestration and DOCX rendering, but not memo judgment.**
   In the default fast path, Python fans out independent Claude analysis
   subprocesses, writes compact artifacts from their structured outputs, then
   asks Claude for the English source package and Chinese completion package.
   In legacy mode (`BSH_MEMO_FAST_PIPELINE=0`), Serena's full skill runs in
   one subprocess. In both modes, Claude emits structured memo content and
   Python validates `logs/memo_package.json`, calls the tracked renderer
   (`server.memo_docx_renderer`), and creates both `.docx` files, validation
   logs, file inventory, and manifest finalization. Per-run renderer scripts
   such as `build_memo.py` are forbidden.

## Where Serena's "company folder" lives in this codebase

Serena's skill text refers to `[BSH Assistant]/[Company Name]/` — a
folder where Serena historically dropped PitchBook PDFs, partner
notes, CB Insights exports, and other research she wanted the memo to
read.

**In this codebase, Serena's folder lives at `data/research/<slug>/`.**
That folder is populated through the **Background Documents** section
of the company page (the `ResearchUploads.vue` component); the backend
is `server/research_store.py`. Memo runs add this folder to Claude's
allowed read paths when it exists, and files there carry a per-doc quick
AI summary in their `index.yaml` row so the analyst can scan the library
without opening every file.

This folder is **distinct** from `data/uploads/<slug>/`:

| Folder | Owned by | UI surface | What lives here |
|---|---|---|---|
| `data/uploads/<slug>/` | the user | "Document Library" panel + per-file Sparkle button | General per-company files (decks, PDFs) the user wants summarized in detail. **Never consumed by the memo flow.** |
| `data/research/<slug>/` | Serena | "Background Documents" panel | Research material Serena drops in for the memo to read. Each file gets a *quick* AI summary (2–3 sentences + 3–5 bullets, single language). |

The memo skill consumes files from `data/research/<slug>/` when they are
present. It must continue to ignore `data/uploads/<slug>/`.

The skill should use the files' raw bytes (via normal Claude file reads
and local conversion helpers where needed), not their quick summaries.
The quick summary is a UI affordance for the analyst, not a memo input.
Re-reading the raw file keeps the memo faithful to the source instead of
summary-of-a-summary.

## Cross-feature checks the code must keep enforcing

- `server/memo_prep.py` must never import from or reference
  `server/files_store.py`, `data/uploads/`, or the upload index.
- `server/memo_analysis.py` and the memo prompt must never list
  `data/uploads/` as an accessible directory.
- The Document Library backend (`server/files_store.py`, deck-summary
  endpoints) must never know that a memo report exists for the
  company.

If a future change creates a coupling between the two, it's a defect.
