# QA Bug Report (July 13, 2026) — Root Causes & Remediation Plan

Source: `BSH Research Center — Bug Test Report (July 13, 2026) by SS.docx`
Target: `https://api.bshventures.com/research/` · Tester: seline.sun@bshfoundation.org
Plan written: 2026-07-14. Root-cause sections (R1–R8) cite line numbers against
`main` @ `d974b16` (pre-fix); the phase sections carry re-verified anchors.

> **STATUS (2026-07-14, evening): ALL PHASES (0–4) ARE DONE.** Implemented and
> verified on `main` (uncommitted): backend 458 pass / 0 fail (the historical
> regen-backoff flake is fixed — Phase 4.8), frontend 133 pass, lint clean,
> build OK. Everything below is historical context.
>
> Remaining actions that are NOT code (user-owned):
> - Run `scripts/qa_2026_07_13_cleanup.py --apply` after reviewing its
>   dry-run output (AMI merge, Alphabet Signs rename, QA test-record
>   deletion, poisoned-cache purge). Dry-run verified 2026-07-14.
> - The Phase 0 ops actions: rotate `BSH_RESEARCH_API_TOKEN` in prod, set
>   real seed-account passwords + `revoke-all`, confirm `BSH_ALLOW_ANON_DEV`
>   unset in prod.
> - ~~Do one live end-to-end memo generation after deploy~~ **DONE
>   (2026-07-14 evening): report `5fa7fd34adf5` (AMI Labs — the QA tester's
>   own July 13 company) ran to `complete` with EN+ZH DOCX, 0 quality-gate
>   P0s, 0 parity blockers. Chinese pass 105s (parallel units, no stall);
>   analysis pipeline ~11 min. The run also surfaced and fixed two more
>   defects: (a) chained-resume bug — a second resume reused the package
>   the quality gate had just rejected because stale `resume_from_*`
>   provenance masked the current failure; fixed with `resume_last_*`
>   fields (endpoint + `_resume` predicate, 2 regression tests); (b) the
>   generator kept writing "at the memo date", tripping the meta-language
>   gate — voice contract now mandates absolute as-of dates and bans
>   memo-self-referencing staleness phrasing. Suite: 460 pass / 0 fail.**
>
> New invariants beyond the Phase 0–1 list below:
> - Company identity matches on evidence: ticker → website/logo host →
>   name/alias (same public/private standing, host-contradiction gate).
>   `storage.resolve_company_match` is the read-only resolver;
>   `deep_search(..., only_company_id=)` restricts refresh persistence.
> - `get_company()` merges per-company sidecars (`data/company_ext/<id>.yaml`,
>   trader_snapshot + translation); `list_companies()` is slim — never read
>   those two fields off list results.
> - `_company_view` exposes canonical `category` (= industry || sector);
>   all five UI surfaces render it.
> - Every mutation route is permission-gated (`_require_permission`);
>   service-role 403 matrix in tests/test_api_auth.py.
> - frontend/tests/i18n.spec.js enforces zero bare template strings on the
>   QA-audited surfaces and a per-file ratchet everywhere else — lower a
>   file's baseline when you fix it, never raise it.
> - Memo runs: atexit marks in-flight runs failed (`failure_phase=shutdown`,
>   auto-resumed at startup); the 30-min orphan sweep demotes stale
>   `analyzing` runs (`failure_phase=orphaned`, human-resumable only).

---

## TL;DR — what the 14 reported bugs actually are

The report lists 14 issues. They collapse into **five root causes**, plus two
findings the tester could not have seen that are more severe than anything they
filed.

| # | Root cause | Reported symptoms it explains |
|---|---|---|
| **R1** | `storage.list_companies()` re-parses a 1.24 MB YAML on *every* call, under a global lock, with no cache | Slow autocomplete (7s), `/api/reports` hangs, sidebar "0 / Loading…" flash, and most of the `/api/jobs/active` 503s |
| **R2** | Four unguarded frontend polling timers, no in-flight guard, no request dedup | 200+ duplicate requests; also the *load* that triggers R1's 503s |
| **R3** | The shared admin API token is injected into public HTML — **and** auth fails *open* if you remove it | "API token exposed in page HTML" (filed [High]; it is Critical) |
| **R4** | `?intake=` is written by the sidebar and read by **nobody** | Dead sidebar Quick Intake buttons *and* broken `?intake=` deep-links (one bug, filed as two) |
| **R5** | Company identity is keyed on an LLM-generated `name` string with exact-match dedup | Duplicate AMI Labs ×3, "Alphabet Inc. (Dallas, TX)", category inconsistency |

**Two things the tester could not see, both worse than their [High]s:**

- **The leaked token authenticates as `admin`.** `product_store.role_for_email(shared_auth=True)` returns `"admin"`. Anyone who views source on the public page gets full admin API access. `server/product_store.py:84-86`.
- **Removing the token makes it *worse*, not better.** `require_api_token` has a dev-mode branch that lets *all* unauthenticated requests through when no token is configured (`server/api.py:337-339`). The obvious "fix" (unset the env var) silently opens the entire API to anonymous admin access. **Do not touch the token without first fixing the fail-open branch.**

And the headline correction on memo generation:

- **Memo generation is not hanging — it takes 19–34 minutes by design, and separately it is failing.** Only 19 of 48 runs on disk ever reached `complete`. The dominant failure is a **180-second silence timeout** that kills the Chinese package pass. The English pass right above it explicitly sets `silence_timeout_sec=600`; the Chinese pass was left on the 180 default. That one missing keyword argument accounts for 6 of the 9 hard failures.

---

## Severity re-ranking

The tester's severities were reasonable given black-box access. With source access, the ranking changes:

| Sev | Issue | Tester's tag |
|---|---|---|
| **P0** | Leaked **admin** token in public HTML + fail-open auth + seeded plaintext passwords | High |
| **P1** | Memo generation: 180s silence timeout kills the Chinese pass (6/9 failures) | (narrative) |
| **P1** | `storage` YAML re-parse — the engine behind 503s, 7s autocomplete, and hangs | Medium/High |
| **P2** | Polling storm (200+ req) | Medium |
| **P2** | Company identity/dedup (duplicates + the Alphabet merge hazard) | Low ×3 |
| **P3** | Intake deep-links + sidebar buttons | Medium ×2 |
| **P3** | Submit-a-link validation; i18n gaps | Medium ×2 |
| **P4** | Upload title append; loading flash | Low ×2 |

The three "[Low] data quality" bugs are upgraded to **P2** because they are the visible surface of a **latent data-destruction bug**: the real Alphabet/Google record (`id: goog`) can be silently overwritten by a Dallas signage company. See R5.

---

# R1 — The storage layer re-parses 1.24 MB of YAML on every call

**This is the single highest-leverage fix in the document.** It is the cause of four separately-reported symptoms.

### The defect

`server/storage.py:71-74`:

```python
def list_companies() -> list[dict]:
    with _LOCK:                                    # process-global RLock (storage.py:36)
        _ensure_dirs()
        return list(_read_yaml(COMPANIES_FILE, []))   # full 1.24 MB yaml.safe_load
```

No cache, no mtime check, no memoization. `get_company(id)` (`storage.py:103-107`) calls it and linearly scans — **a 1.25-second full-file parse to fetch one record.**

Measured on this repo against real data (`data/companies.yaml` = 1,239,021 bytes / 73 companies):

| Call | Time |
|---|---|
| `storage.list_companies()` | **1253 ms**, every call |
| `storage.get_company(id)` | **1246 ms** |
| `companies_autocomplete.autocomplete("nex")` warm | **1259 ms** |
| `companies_autocomplete._load_researched()` (30s TTL) | **1789 ms** |

The file is that big because `trader_snapshot` (864 KB) and `translation` (327 KB) are stored **inline** in the same file — 96% of the bytes, none of which the sidebar or autocomplete needs.

### What it explains

- **Autocomplete 7s** — every keystroke pays the 1.25s parse (`companies_autocomplete.py:283` → `storage.search_companies`), plus a 1.79s cache-dir rescan when the 30s TTL expires (`companies_autocomplete.py:123,130-177`), plus lock-wait behind the 4-second `/api/companies` poll. 1.25 + 1.25 + 1.79 + wait ≈ 7s. The frontend debounce is fine (220ms, `HomeView.vue:74-94`) — not the problem.
- **`/api/reports` "hangs"** — the handler itself is fast (114 ms). It is *starved*: it takes the **same global `_LOCK`** (`storage.py:388`) that `list_companies()` holds for 1.25s at a stretch.
- **`/api/jobs/active` 503** — see R2; this endpoint calls `get_company()` **inside a per-job loop** (`api.py:3680`, `:4028`, `:4354`), so 3 active jobs = ~4 seconds of lock thrash, polled every 3 seconds. It never drains.
- **Sidebar "0 / Loading…" flash** — the flash window is exactly as long as the first `/api/companies` takes. Fix the parse and it collapses to a single frame.

### Fix

1. **Memoize `list_companies()` on `(mtime, size)` of the file.** ~15 lines. Takes the call from 1253 ms → ~0 ms and fixes most of R1's downstream symptoms outright.
2. **Split `trader_snapshot` and `translation` out** into per-company files (`data/companies/<id>/`), and drop them from `_company_view()` (`api.py:6449-6450`) unless explicitly requested. This shrinks the hot index file from 1.24 MB to ~50 KB *and* stops shipping ~1.2 MB to the browser every 4 seconds.
3. **Replace the coarse global `_LOCK`** with per-file locks, or make reads lock-free off an mtime-validated snapshot so readers never block each other.
4. **Hoist `get_company()` out of the loops** at `api.py:3680`, `:4028`, `:4354` — build one `{id: name}` map per request.
5. **Cache `list_reports()` on directory mtime**; paginate `/api/reports` (`api.py:1892-1894` reads every report YAML, unpaginated) and add `ETag`/`304`.
6. **Autocomplete:** build the local+researched index once at startup, refresh in a background task, never on the request path (`companies_autocomplete.py:130-177`). Prefetch the SEC EDGAR index in a startup hook and **stop holding `_INDEX_LOCK` across the 8s network fetch** (`companies_autocomplete.py:46-51`).

---

# R2 — The polling storm (200+ duplicate requests)

Not a `useEffect`/watcher dependency loop, as the report speculated. It is **four independent unguarded timers**.

| Endpoint(s) | Caller | Interval |
|---|---|---|
| `/api/reports`, `/api/companies`, `/api/external/feed`, `/api/external/hormuz` | `App.vue:54` `setInterval(refreshAll, 4000)` | **4s × 4 endpoints** |
| `/api/jobs/active` | `ActiveJobsRail.vue:66` | 3s |
| `/api/jobs/active` | `ResearchUploads.vue:241` | 2s |
| `/api/jobs/active` | `WeeklySummaryView.vue:218` | — |

Steady state: **~80 requests/minute.** A 2.5-minute session = 200+. The tester's count needs no loop to explain it.

**Why it degenerates ("runaway"):** `refreshAll` (`App.vue:24-45`) has **no in-flight guard**. `ActiveJobsRail.vue:33-38` correctly has one (`let polling = false`); `App.vue` does not. Because `/api/companies` takes 1.25s+ server-side and contends on R1's global lock, a cycle routinely exceeds the 4s interval — so `setInterval` fires the next cycle while the previous is still outstanding and they **stack**. Against the browser's 6-connections-per-origin limit, that produces exactly the "pending" symptom filed against `/api/reports`.

`api.js:98-129` (`request()`) is a bare `fetch` wrapper: no in-flight promise map, no ETag, no TTL cache.

**Note the sidebar was exonerated** — `Sidebar.vue` is mounted once and is purely prop-driven. The report's "sidebar re-fetching on every render" hypothesis is wrong.

### Fix
1. In-flight guard on `refreshAll` (mirror `ActiveJobsRail.vue:33`), and pause polling on `document.hidden`.
2. Consolidate the three `/api/jobs/active` pollers into **one shared store** with a single timer.
3. Raise the sidebar interval to 20–30s, or drop the timer and refresh off the existing `@reports-changed` event (`App.vue:259`).
4. Add an in-flight/TTL dedupe layer to `api.js` `request()`, keyed on method+path.
5. `App.vue:26` — swap `Promise.all` → **`Promise.allSettled`**. Today, if *any* of the four calls rejects, **none** of the assignments run: the sidebar blanks to 0 even though `/api/companies` succeeded.

---

# R3 — [P0] Leaked admin token, fail-open auth, seeded passwords

The tester filed the meta tag as [High]. It is **Critical**, and it comes with two adjacent defects that make the naive fix dangerous.

### R3a. The tag is server-injected and the value is the live production secret

`server/main.py:308-315`:

```python
html_text = index_path.read_text(encoding="utf-8")
metas: list[str] = []
token = _expected_token()                    # → os.environ["BSH_RESEARCH_API_TOKEN"]
if token:
    metas.append(f'<meta name="bsh-research-api-token" content="{_html.escape(token, quote=True)}">')
```

So `BSH-8688` is the **literal production value** of `BSH_RESEARCH_API_TOKEN` — not a placeholder, not a nonce, not a CSRF token. It is absent from local `.env`, which is why dev never shows it.

The docstring at `main.py:298-300` states the design assumption out loud: *"anyone who can already load the HTML can also call the API."* That assumption is the vulnerability — the HTML is public, therefore the API is public.

### R3b. The token grants **admin**

`require_api_token` gates every `/api/*` route (`api.py:369`). Its fast path (`api.py:342-344`) accepts the shared token with no user, no session, no expiry, no scoping. Then `/api/auth/me` resolves that caller via `product_store.role_for_email(email=None, shared_auth=True)` — `server/product_store.py:84-86`:

```python
def role_for_email(email: str | None, *, shared_auth: bool = False) -> str:
    if shared_auth and not email:
        return "admin"
```

**The leaked token is an admin credential.** It is 8 characters (`BSH-8688`), structurally guessable, never rotates, and there is no rate limiting anywhere (login at `api.py:390-408` is unthrottled). It is also appended as a `?token=` **query parameter** for SSE and download links (`api.js:76-82`, accepted at `api.py:318-322`) — so it lands in nginx access logs, browser history, and `Referer` headers.

### R3c. ⚠️ Removing the token opens the API completely

`server/api.py:337-339`:

```python
# Dev mode: no env token configured AND no session token presented →
# let everything through so local-only development still works.
if not expected and presented is None:
    return
```

If someone "fixes" the leak by unsetting `BSH_RESEARCH_API_TOKEN`, **every `/api/*` route becomes anonymously accessible — as admin** (per R3b, `shared_auth and not email` → `"admin"`). This is a trap. **Fix the fail-open branch first, then rotate.**

### R3d. All eight real accounts share a plaintext seeded password

`server/auth_store.py:42-53` seeds `robert@bshventures.com`, `serena@bshfoundation.org`, and six others with the shared password `"redapple"` (plus `guest`/`guest`). **This is in git history.**

### Fix — in this order
1. **Make auth fail closed.** Delete the `api.py:337-339` branch, or gate it behind an explicit `BSH_ALLOW_ANON_DEV=1` env flag never set in prod. *Do this before step 2 or you will open the API.*
2. **Delete the meta-tag injection** (`main.py:308-315`). Keep the `bsh-research-api-base` meta — the `/research` base path needs it.
3. **Switch to a cookie session.** `POST /api/auth/token` already mints a hashed, expiring token via `auth_store.issue_session` (`auth_store.py:253-277`). Have it also `set_cookie(httponly=True, secure=True, samesite="lax", path="/research")`, and have `require_api_token` read `request.cookies` first. The app is same-origin under `https://api.bshventures.com/research/`, so cookies make the `?token=` query-param hack unnecessary — `EventSource` and `<a href>` downloads send cookies automatically. Then delete `api.js:76-82` and the `token: str | None = Query(...)` param at `api.py:329`. Add a CSRF guard (or `SameSite=strict`) for mutations once cookies carry auth. Note: cookie `Path` must match the mount (`root_path="/research"`, `main.py:86`).
4. **Rotate `BSH_RESEARCH_API_TOKEN`.** Treat `BSH-8688` as burned. If a machine-to-machine token is still needed (per `docs/ios-app-implementation.md`), make it a long random secret held only by that client, never rendered into HTML, and give it a **non-admin** role rather than the `shared_auth → "admin"` shortcut.
5. **Force a password reset** for all seed accounts; remove the plaintext list at `auth_store.py:42-53`; add rate limiting/lockout to login.

### On the `/api/jobs/active` 503 (filed [High])

**There is no `503` anywhere in the API layer.** An exhaustive grep finds exactly two, both in `server/main.py` (:104, :302-307), both meaning "frontend build missing" — neither can serve `/api/jobs/active`. Auth failure is **401**, not 503 (`api.py:364-367`). The SPA catch-all explicitly raises **404** for `api/` paths (`main.py:391-399`).

So the 503 is emitted **by the layer in front of the app** — uvicorn's `--limit-concurrency` (which returns 503 when N in-flight requests is exceeded) or nginx `limit_req`/`limit_conn`/"no live upstreams". `run.sh:41` forwards arbitrary flags (`exec uv run uvicorn server.main:app ... "$@"`), so the prod invocation is not visible in-repo.

**The overload is real and in-repo, though**, and it is what to fix: `/api/jobs/active` is a `def` (threadpool, 40-thread cap) that on *every call* runs three `recover_stale_runs` sweeps (`api.py:4440-4453`) — one of which takes a module-global `RLock` and `yaml.safe_load`s every session file (`serena_analysis.py:547-564`) — then walks **17** glob-based generators across a **2.1 GB** `data/` tree. It also performs *writes* on every poll. Multiply by three pollers at 2–3s (R2) and the concurrency limit is reached; the front layer 503s before the request ever reaches the handler.

**Fix:** cache the scan behind a 2–5s TTL (or an in-process job registry updated by writers), and **move the `recover_stale_runs` sweeps out of the request path** into the startup hook plus a periodic background thread. Recovery-on-a-read-endpoint is the core design error. Then confirm the prod `--limit-concurrency` / nginx `error_log` to close the loop.

---

# R4 — Intake deep-links and dead sidebar buttons (one bug, filed as two)

`?intake=` is **written by exactly one place and read by nobody.**

Producer — `Sidebar.vue:161-181`:
```vue
<RouterLink :to="{ name: 'home', query: { intake: 'link' } }"> … Submit Link
<RouterLink :to="{ name: 'home', query: { intake: 'upload' } }"> … Upload Research
<RouterLink :to="{ name: 'home', query: { intake: 'note' } }"> … Add Internal Note
```

Plain `RouterLink`s — no handler, no emit, no shared state. They navigate to `/` and pick up `router-link-active` styling. **That styling is the entire observed effect** — exactly the tester's "only highlights the button."

Consumer — **none.** `grep -rn "query.intake" frontend/src` returns nothing. `HomeView.vue:3` imports only `useRouter`, never `useRoute`.

The state that *would* need driving is private to each tool and has no external control surface — `SubmitLinkTool.vue:20`, `UploadResearchTool.vue:19`, `AddHormuzResearchTool.vue:21` each hold a local `const expanded = ref(false)` toggled only by their own header button. None declares an `expanded` prop or `defineExpose`; `HomeView.vue:456-458` renders all three with **no props at all**.

**The sidebar buttons *are* the deep-links** — fixing the query-param handling fixes both reported bugs with one mechanism.

### Fix
Give each tool `defineModel('expanded')` (replacing the local ref). In `HomeView.vue`, add `useRoute()` plus `linkOpen`/`uploadOpen`/`noteOpen` refs and:

```js
watch(() => route.query.intake, (v) => {
  linkOpen.value   = v === 'link';
  uploadOpen.value = v === 'upload';
  noteOpen.value   = v === 'note';
}, { immediate: true });
```

Bind `v-model:expanded` on the three components, and `scrollIntoView` the Quick Add panel.

---

# R5 — [P2, was Low] Company identity is keyed on an LLM-generated string

The three "[Low]" data bugs share one root cause, and it hides a **data-destruction hazard**.

### R5a. Dedup is exact string equality on a normalized name — nothing else

`storage.upsert_company_from_match()` (`storage.py:282-377`) is the **only** company-creation path. Its match loop (`:300-309`):

```python
if ticker and c_ticker and ticker == c_ticker:   # needs BOTH tickers
    found_idx = i; break
if norm_name and norm_name == c_name_norm:       # exact equality only
    found_idx = i; break
```

For a **private** company `ticker` is `None`, so everything rests on exact normalized-name equality. `website` and `logo_domain` are collected into `enrichment` (`:311-332`) but **never used as match keys**. `aliases` is hardcoded to `[]` on create (`:369`), so that path is dead too.

### R5b. The suffix regex is anchored to `$`, so a trailing parenthetical defeats it

`storage.py:232-236` — `_LEGAL_SUFFIX_RE` ends in `\.?$`. Trace the three real AMI records:

| `name` in companies.yaml | normalized key | slug |
|---|---|---|
| `Advanced Machine Intelligence Labs (AMI Labs)` | `advanced machine intelligence labs ami labs` | `…-labs-ami-labs` |
| `Advanced Machine Intelligence, Inc. (AMI Labs)` | `advanced machine intelligence **inc** ami labs` | `…-inc-ami-labs` |
| `Advanced Machine Intelligence Labs, Inc.` | `advanced machine intelligence labs` | `…-labs-inc` |

Because `(AMI Labs)` trails the `Inc.`, the `$` anchor never matches and `inc` survives *mid-key*. **Three different keys → three `found_idx = None` → three records.**

### R5c. The refresh endpoint feeds the AI's own output back in as the query — the amplifier

`api.py:1771-1793` (`_refresh_company_summary`):

```python
name = company.get("name") or ""                                   # ← AI-generated
result = companies_ai.deep_search(name, force_refresh=True, ...)   # ← replayed verbatim
chosen = next((m for m in matches if m.get("id") == company_id), None)
if chosen is None and matches:
    chosen = matches[0]        # ← silently accepts a DIFFERENT company id
```

`deep_search` upserts **every** returned match (`companies_ai.py:299`). The prompt asks for the "legal/canonical name" — a non-deterministic LLM judgment. So: refresh → new name variant → new key → **new record minted** → *that* record's name becomes the next refresh's query.

The cache is the receipt. Four `companies_ai` cache entries exist keyed on query string, and keys 2–4 are not things a human typed — they are AI-generated `name` fields replayed as queries:
```
→ ami labs
→ advanced machine intelligence labs (ami labs)
→ advanced machine intelligence, inc. (ami labs)
→ advanced machine intelligence labs, inc.
```
Line 1788's `chosen = matches[0]` is the smoking gun: the code **detects** the refreshed match has a different id and proceeds anyway, without merging or deleting.

### R5d. ⚠️ The latent bug: the real Alphabet/Google record can be destroyed

`alphabet-inc-dallas-tx` (`industry: Signage & Visual Communications`, `website: alphabetsigns.com`, `ticker: null`) is really *Alphabet Signs of Dallas*. The model fabricated the legal-sounding `Alphabet Inc. (Dallas, TX)` because `SYSTEM_PROMPT` gives two conflicting instructions — "disambiguate ambiguous queries" (`companies_ai.py:200-202`) and "use the legal/canonical name" (`:205-207`) — and the schema has **no field for a disambiguator**, so it smuggled the location into `name`.

**Had the model instead returned plain `"Alphabet Inc."`** — which the canonical-name instruction actively pushes it toward — then:
- `_normalize_company_name("Alphabet Inc.")` → `"alphabet"`, which **equals the key for `id: goog`**.
- The signage company has `ticker: null`, so the ticker guard at `storage.py:304` is skipped and the **name branch matches `goog`**.
- The merge loop (`storage.py:336-344`) then overwrites unconditionally — only `description` and `sector` are guarded (`:345-348`). `industry`, `hq`, `website`, `logo_domain`, `founded_year`, `products`, `competitors` are **not**.

**Google would silently become a Dallas signage manufacturer.** Today that is one LLM naming coin-flip away. This is why the "[Low]" tags are wrong.

### R5e. Category inconsistency is a UI contract gap, not a data conflict

The `aapl` record legitimately carries **both** fields (`data/companies.yaml:10107-10117`): `sector: Technology`, `industry: Consumer Electronics`. The surfaces disagree about which is "the category":

| Surface | File:line | Renders |
|---|---|---|
| Search typeahead | `HomeView.vue:425` — `s.sector` | Technology |
| Company card | `CompanyCard.vue:88` — `company.sector` | Technology |
| Detail page | `ResearchView.vue:688-691` — `industry \|\| sector` | Consumer Electronics |
| Sidebar | `Sidebar.vue:225` — `industry \|\| sector \|\| …` | Consumer Electronics |

Compounding: neither field has a controlled vocabulary (`companies_ai.py:43-44` — free-text, nullable, no `enum`), so the model mixes taxonomies across records — `aapl.sector: Technology` (colloquial) vs `goog.sector: Communication Services` (GICS). Two megacap tech companies, two classification systems, same column.

### Fix
1. **Add stable identity keys** to the match loop (`storage.py:300-309`) **before** the name comparison: normalized `website` host and `logo_domain`. All three AMI records carry `ami.xyz` — this alone collapses them.
2. **Never match a tickerless candidate onto a record that has a ticker** (invert the guard at `storage.py:304`). A private company must not merge into a public one on name alone. *This is the fix that saves `goog`.*
3. **Gate the merge** (`storage.py:336-344`) on corroborating identity — if `website`/`logo_domain` hosts disagree (`abc.xyz` vs `alphabetsigns.com`), it is a *different company*, not an enrichment.
4. **Drop the `$` anchor** in `_LEGAL_SUFFIX_RE`; strip parenthetical segments before comparing; index the parenthetical (`AMI Labs`) into `aliases` and match against it.
5. **Never let refresh mint a sibling.** At `api.py:1786-1789`, when `chosen is None`, abort or merge explicitly — remove the `matches[0]` fallback. Refresh by a **stable key** (ticker/website/logo_domain), not the mutable AI `name`.
6. **Add `legal_name` / `display_name` / `disambiguator` to `SCHEMA`** (`companies_ai.py:26-192`) so "Dallas, TX" has somewhere to live. Derive the slug from `legal_name` + `logo_domain`.
7. **One canonical category:** add a computed `category = industry or sector` to `_company_view()` server-side and render `company.category` from all five call sites. Constrain `sector` to a GICS `enum`.
8. **Data cleanup (one-off):** merge the three AMI records; rename `alphabet-inc-dallas-tx` → `Alphabet Signs`; delete the QA test records the report lists (internal note "TEST - please delete", the example.com link, the `BSH_TEST_please_delete.txt` upload).

---

# R6 — Memo generation: not a hang, a 180-second timeout

The report says *"never completes in a single test process."* Two separate truths:

### It genuinely takes 19–34 minutes

From `created_at` → `updated_at` on `status: complete` runs:

| Report | Wall clock |
|---|---|
| `1a6355a76710` | **34m 06s** |
| `2179544f950c` | 29m 58s |
| `3102bdfc80a8` | 32m 28s |
| `13bde9d04c4d` | 19m 14s |

No test sitting will see this finish by accident. **That is partly a product bug**: a 30-minute job with no ETA, no phase breakdown, and no "you can close this tab" affordance is indistinguishable from a hang.

### And it is also failing outright — 19 of 48 runs ever completed

```
19  complete
12  analyzing                 ← stuck forever at progress 15
 9  failed_during_analysis
 4  failed_scope_check
 4  failed_quality_gate

 6  error: memo Chinese package stalled after 180s without output   ← dominant
 2  error: memo package resume stalled after 180s without output
```

### R6a. [P1] The missing keyword argument

`claude_runner.py` — the English package pass explicitly raises its silence budget; **the Chinese pass, directly below it, does not:**

```python
# run_memo_fast_english_package (claude_runner.py:3534)
        timeout_label="memo English package",
        timeout_sec=timeout_sec,
        silence_timeout_sec=600,          # ← explicitly raised

# run_memo_fast_bilingual_package (claude_runner.py:3640-3647)
        timeout_label="memo Chinese package",
        timeout_sec=timeout_sec,          # 1200
        # ← silence_timeout_sec omitted → inherits the 180 default (:3345)
```

The kill is at `claude_runner.py:1490-1495`: `if now - last_event_at > silence_timeout_sec`. `last_event_at` only advances on a **stream-json event**. The bilingual pass hands Claude the entire English package and asks it to fill every Chinese string — one enormous, tool-free, single-block generation that publishes no intermediate events. The wall clock crosses 180s of "silence" while the model is working perfectly well. **The 1200s wall budget is never reached; the silence guard fires first, every time.**

Precedent confirms this is an oversight, not a design: PDF translation — a comparably long single generation — explicitly sets `silence_timeout_sec=300.0` (`claude_runner.py:2187`). The *longest* single generation in the system was left on the default.

**Fix:** pass `silence_timeout_sec=600` to the bilingual pass (`claude_runner.py:3647`) **and** replace the hardcoded `180` on the resume pass (`claude_runner.py:4326` — the source of the 2 "memo package resume stalled" errors), matching the English pass. Better: treat partial `content_block_delta` traffic as liveness so the guard measures *true* stalls. **These two call sites account for 8 of the 9 hard failures on record.** Concrete task: Phase 1.1.

### R6b. A bare daemon thread — a restart orphans the run permanently

`memo_analysis.py:2963-2972` — `threading.Thread(..., daemon=True)`. A `--reload`, Ctrl-C, or restart kills it mid-flight with no `atexit` and no terminal event. The report freezes at `status: analyzing, progress: 15` **forever** — the 12 stuck records (four of them frozen at the same 05:36 timestamp on 2026-06-23: one restart took out four runs at once).

The startup sweep does not rescue them. `recover_stale_reports` (`memo_analysis.py:2833-2864`) only repairs runs that *already* have a successful Claude result:

```python
result = stream_state.get("success_result")
if not result:
    continue          # ← killed mid-generation → skipped, stays "analyzing" forever
```

So they are invisible to the resume path too (`api.py:2248-2265` requires `status.startswith("failed")`).

**Fix:** move `start_analysis` onto a supervised worker/process, or at minimum register an `atexit`/signal handler that writes a terminal `error` event. Extend `recover_stale_reports` to **demote** any `analyzing` report whose `stream.jsonl` has been idle beyond a threshold into `failed_during_analysis`, making it resume-eligible.

### R6c. The frontend gives up on the first transient poll error

`ResearchView.vue:469-507`:

```js
async function pollReport() {
  try { const r = await api.getReport(activeReport.value.id); … }
  catch (e) { stopPolling(); }      // ← line 488: ANY error permanently kills polling
}
```

Polling is **1/second for 30+ minutes** (~1,800 requests) and a **single** failure — a dev-server reload, a laptop sleep, a `GET /reports/{id}` racing `storage._write_yaml`'s `tmp.replace()` (`storage.py:57-62`) — kills it with no retry and no backoff. `startPolling()` is only re-armed from `generate()` (line 540). The UI then sits at its last-seen progress indefinitely **even when the backend finishes normally.**

**And the good channel is wired to nothing:** a real SSE stream exists at `GET /api/memos/{report_id}/stream` (`api.py:2332-2400`) with a correct 600s idle deadline that resets on every chunk. `grep -rn "memos" frontend/src` returns one unrelated hit. **The frontend never consumes it.**

**Fix:** bounded retry with backoff instead of the unconditional `stopPolling()`, plus a "reconnecting…" state. Then migrate the memo UI onto the existing SSE stream — it replays from the start of `stream.jsonl`, so a mid-run reload recovers full progress history instead of losing it.

### R6d. Worst-case budget ≈ 90 minutes

Phases 3 (English package, `× (1 + 1 retry)` = 2400s ceiling) and 4 (bilingual, 1200s) are **strictly serial**; only phase 2 is parallelized (`ThreadPoolExecutor(max_workers=4)`, `memo_analysis.py:2364`). Meanwhile `ACTIVE_JOB_MAX_IDLE_SECONDS` defaults to 1800 (`api.py:82-84`), so the jobs rail declares a legitimately-running memo "not in flight" if any phase goes 30 min without a stream event.

**Fix:** the bilingual pass is a pure translation of phase 3's output — split it per-section and fan it out across the same executor. Nothing requires one 20-minute monolithic call.

**Ruled out:** no nginx config in-repo; `run.sh:41` sets no `--timeout-keep-alive`; uvicorn imposes no per-request timeout. `POST /api/reports` returns as soon as `bootstrap_memo_run` finishes (its scope check is a pure heuristic, no LLM call). The long work is all in the background thread — **the timeouts that matter are the ones inside `claude_runner`.**

---

# R7 — Localization: 100% dictionary parity, ~60 hardcoded strings

**The i18n layer is not broken and no `zh` value is missing.** I parsed both blocks of `frontend/src/i18n.js`: **596 `en` keys, 596 `zh` keys, 0 gaps.** Every symptom is a **template string that was never keyed** — `t()` is never called on it.

`t()` (`i18n.js:1338-1343`) falls back `zh → en → raw key`, silently. That silence is why this shipped.

### Inventory

**`Sidebar.vue`** (imports `useT` at :21 — `t` is in scope, just unused):
`Quick Intake` (:159) · `Submit Link` (:166) · `Upload Research` (:173) · `Add Internal Note` (:180) · `Companies` (:187) · `Portfolio`/`Pipeline`/`Top Players` (:95-97, JS labels) · `No companies yet.` (:208) · `Show less`/`Show all N` (:240-241) · `Market Radar` (:253) · `Stock`/`Public market research` (:286-287) · `Innovation Lab` (:294) · **`Settings` (:306)** · **`Profile` (:313)**

> The `:95-97` labels are inside a `computed`, so swapping them to `t()` stays reactive. **Do not hoist them to a module constant** — that would break reactivity on language change.

**`HomeView.vue`**: **`Operations` (:596)** and its hint (:598). Everything else in that section is correctly keyed, which is why only the heading looks broken.

**`App.vue`** — **does not import `useT`/`t` at all**:
- `tabLabel()` (:93-100) hardcodes `Documents / Memo Studio / Company News / Industry Views / Co-Pilot / Overview` — **even though `research.tab_news` etc. exist in both `en` (:410) and `zh` (:1072, `"公司新闻"`)**. Clearest "key exists, never used" case.
- `breadcrumbs` (:102-137, fallback :201) hardcodes every crumb.
- *Why the tabs looked translated:* the real tab strip is `ResearchView.vue:307-311` and **does** use `tr()`. App.vue's header duplicate does not.

**Company News panel — `ResearchView.vue:1286-1408`** (imports `useT` as `tr` at :23 — **and bypasses it entirely**). All 16 strings hardcoded: heading (:1293), `Reverse-chronological feed` (:1295), `Submit Link` (:1306), `placeholder="Search news, sources, summaries"` (:1317), `aria-label`s (:1323, :1333), `All categories`/`All tags` (:1325, :1335), `Filter`/`Reset` (:1345, :1352), loading (:1359), empty state (:1365), `Open source` (:1396).

### Company News: the *content* is English-only too

`GET /api/companies/{id}/news-feed` (`api.py:2906-2921` → `context_store.py:168-221`) takes **no `lang` param**, and `api.js:184-191` never sends one. `title`/`summary`/`category` come back in English regardless of `appLanguage`.

**Translations already exist and are ignored.** `company_translate.py:206-209` translates `recent_news` into `company["translation"]`, but `company_news()` reads `company.get("recent_news")` (`context_store.py:180`) and **never consults `company["translation"]["recent_news"]`**. `CompanyDetail.vue:29-55` shows the correct pattern.

`context_store.py:219` also hardcodes a **server-side English UI string** that leaks straight into the panel: `"empty_state": "Submit a link to archive source-attributed company news."`

External-archive rows (`context_store.py:182-184`) have no `zh` at all and would need a real translate pass — `external_translate.py` only handles research PDFs.

### The test gap that let this ship

`frontend/tests/i18n.spec.js` **cannot catch any of it.** It parses `i18n.js` *source only* and never opens a `.vue` file. It asserts `console.*` and `research.tab_*` have `zh` counterparts — which all pass, because dictionary parity is already 100%. The bugs are all at the **call sites**.

### Fix
1. Add the ~40 missing keys to both blocks; **reuse existing keys where they exist** (`research.tab_news`, `home.tag_tracked`, `sidebar.untitled`, `sidebar.external_source`).
2. Wire the call sites above. Import `useT` into `App.vue`.
3. Server: drop the English `empty_state` from `context_store.py:219` (return a code; let the client render `t("news.empty")`); plumb `lang` through `api.js:184-191` → `api.py:2906` and have `company_news()` prefer `company["translation"]["recent_news"]` when `lang=zh`.
4. **Harden the test** — this is the fix that prevents regression: add (a) a global "every `en` key has a `zh` key" assertion, and (b) **a lint that scans `src/**/*.vue` template blocks for bare ASCII text nodes and `placeholder=`/`aria-label=`/`title=` attributes containing `[A-Za-z]{3,}` outside `{{ t(…) }}`**, with an allowlist for brand strings (`Berkeley Summit House`, `BSH`, tickers). That check is what would have caught all ~60.

---

# R8 — The two remaining form bugs

### Submit-a-link: no validation feedback

`SubmitLinkTool.vue`. **The error state and spinner both exist and are rendered** (`error` ref :24 → `<div v-if="error">` :114; `Loader2 v-if="previewing"` :109). They are simply never reached:

- **Empty:** the button is `:disabled="!url.trim()"` (:106), and `runPreview` silently early-returns anyway (`:43` — `if (!url.value.trim()) return;`).
- **Invalid (`not-a-real-url-xyz`):** the input is `type="url"` (:100) inside `<form @submit.prevent="runPreview">` (:97) **with no `novalidate`**. `v-model` still takes the raw string (so the button enables), but **native constraint validation cancels the submit event** — `runPreview` is never invoked. No spinner, no network call, no error. There is zero client-side URL validation in the component.

The backend is fine (`api.py:4702-4708` raises 400 for empty/failed; `api.js:117-127` throws on non-2xx). A valid-but-*dead* URL *would* surface an error — a client-side-invalid one never gets that far.

**Fix:** change the input to `type="text"` (or add `novalidate`), drop the empty-disable, and replace the early `return` with real validation — set `error.value = t('submit_link.url_required')` when empty, and `try { new URL(url.startsWith('http') ? url : 'https://' + url) } catch { error.value = "Enter a valid URL" }` — mirroring the server's own `https://` prefixing at `api.py:4705`.

### Upload title appends instead of replaces

`UploadResearchTool.vue:33-38`:
```js
if (!title.value) title.value = f.name.replace(/\.[^.]+$/, "");   // :37
```
**No concatenation and no competing watcher.** The filename is written into the **value** of the `v-model="title"` input (:118), while the placeholder (:119, "Title (defaults to filename)") advertises it as a *hint*. The user clicks in, the caret lands at the end of `my-deck`, and typing yields `my-deckReal Title`.

The prefill is also **redundant** — the backend already defaults to the sanitized filename when the field is empty (`api.py:5537`: `"title": (title or "").strip() or safe_name`).

**Fix (preferred):** **delete line 37.** The field starts empty, the placeholder explains the default, the server fills it in. Typing behaves normally. If a visible prefill is wanted instead, track a `titleAutofilled` flag and `e.target.select()` on first focus.

---

# Handoff context for a fresh session — READ THIS FIRST

**Phases 0 and 1 are DONE** (2026-07-14, status banners in each section below).
**Start at Phase 2.** As of writing, all Phase 0–1 changes sit **uncommitted on
`main`** — confirm with the user whether to commit them before starting new work
(CLAUDE.md: work directly on main, commit when asked, `Co-Authored-By: Claude` trailer).

## Invariants Phases 0–1 introduced (do not regress these)

**Auth (Phase 0):**
- `require_api_token` (server/api.py) **fails closed**. Anonymous access only via
  `BSH_ALLOW_ANON_DEV=1` (local dev; set in `.env` along with `BSH_COOKIE_SECURE=0`).
- Credentials: session bearer header, session **httponly cookie** (`bsh_session`,
  set on login, used by downloads/SSE), or the shared env token (header-only).
- `request.state.auth_kind` is set to `"anon_dev"` / `"shared"` by the dependency;
  `_caller_role()` maps anon_dev→`admin` (local escape hatch), shared→**`service`**
  (read-only role in product_store.ROLE_PERMISSIONS). The shared token is never admin.
- Cookie-authenticated **mutations require the `X-BSH-Client` header** (CSRF guard);
  `apiFetch` in frontend/src/api.js sends it unconditionally. Any new fetch that
  bypasses `apiFetch` for a mutation must send it too.
- `withApiToken()` in api.js is now a **plain alias of `withBase()`** — there is no
  `?token=` query-param channel anywhere. Don't reintroduce one.
- No credential is ever injected into served HTML (only `bsh-research-api-base`).
- Login is rate-limited (5 fails/15min per email → 429); `must_reset` flag exists;
  operator CLI: `python -m server.auth_store {set-password,create-user,list,revoke,revoke-all}`.
- `/api/companies/regen-all` and `/api/companies/trader/refresh-all` are gated with
  `_require_permission(request, "tasks:action")`. **~75 other mutation routes remain
  ungated — that sweep is Phase 4.1.**

**Storage caches (Phase 1):**
- `storage.list_companies()/get_company()/company_names()/search_companies()` serve
  from an in-memory cache keyed on `companies.yaml`'s `(mtime_ns, size)`;
  `list_reports()` has a per-file cache. All public accessors **deepcopy** what they
  return — never hand out cached objects directly, and never mutate what a cached
  accessor returned expecting it to persist (write via `update_company`/`_write_yaml`,
  which bumps mtime and self-invalidates the cache).
- `storage.company_names()` is the cheap `{id: name}` map — use it instead of
  `get_company()` in loops.

**Jobs endpoint (Phase 1):**
- `GET /api/jobs/active` **no longer runs recovery**; it reads state behind a 3s TTL
  cache (`_active_jobs_cache`). Recovery lives in `api.recover_stale_jobs()`, driven
  by `start_stale_job_recovery()` (startup + 60s background thread, wired in
  server/main.py). Tests that need recovery call `api.recover_stale_jobs()` directly;
  `tests/conftest.py` resets `_active_jobs_cache` between tests (keep that).

**Frontend polling (Phase 1):**
- `frontend/src/activeJobs.js` owns the ONE `/api/jobs/active` poll (3s,
  reference-counted, pauses on `document.hidden`). ActiveJobsRail and ResearchUploads
  consume its shared ref — new consumers must subscribe, not add their own timer.
- `App.vue`'s `refreshAll` has an in-flight guard, uses `Promise.allSettled`, polls at
  20s, pauses when hidden. `@reports-changed` still triggers immediate refresh.

**Memo pipeline (Phase 1):**
- `claude_runner.MEMO_PACKAGE_SILENCE_TIMEOUT_SEC = 600` governs the English,
  bilingual, and resume package passes (guarded by `tests/test_memo_package_timeouts.py`).

**Test-suite facts:**
- `tests/conftest.py`'s autouse fixture sets `BSH_ALLOW_ANON_DEV=1` and clears the
  jobs TTL cache. Auth tests (`tests/test_api_auth.py`) override env themselves.
- **Known pre-existing flake:** `tests/test_trader_snapshot.py::test_regen_all_proactively_backs_off_at_usage_window_guard`
  fails on baseline `main` too (verified via git stash). Not a regression signal.
  Fixing it is Phase 4.8.
- Verify with: `.venv/bin/python -m pytest -q` (expect 400 pass / that 1 flake) and
  `cd frontend && npm test && npm run lint && npm run build` (120 pass).
- Live smoke: `BSH_COOKIE_SECURE=0 .venv/bin/python -m uvicorn server.main:app --port 8079`
  (startup takes a few seconds — it materializes local state), then curl
  `/api/companies/autocomplete?q=app` (~5ms warm), `/api/reports` (~20ms).

**Outstanding ops actions (user-owned, not code):** rotate `BSH_RESEARCH_API_TOKEN`
in prod (BSH-8688 is burned), set real seed-account passwords + `revoke-all`, confirm
`BSH_ALLOW_ANON_DEV` unset in prod. The user said "we don't need to do those yet."

---

# Sequenced work plan

Five phases, each independently shippable. Ship and verify each phase before starting the next — Phase 0 changes the auth substrate everything else runs on, and Phase 1 changes the load profile that Phase 0's rate limiting will see.

Conventions used below:
- **Change** — what to do, concretely.
- **Done when** — the acceptance check. Every task has one that can be verified mechanically or in one manual step.
- Backend tests live in `tests/` (pytest); frontend tests in `frontend/tests/` (`npm test` = vitest). Run `pytest` and `cd frontend && npm test && npm run lint` at each phase boundary.

---

## Phase 0 — Security lockdown

> **Status: DONE (2026-07-14).** Implemented on `main`. Backend 390 pass / 1
> pre-existing flake (`test_regen_all_proactively_backs_off_at_usage_window_guard`,
> fails identically on baseline). Frontend 120 pass, lint clean, build OK. Live
> auth matrix verified against uvicorn. New tests in `tests/test_api_auth.py`.
> **Remaining ops actions (not code):** rotate `BSH_RESEARCH_API_TOKEN` in prod,
> set real passwords for seed accounts + `revoke-all`, confirm `BSH_ALLOW_ANON_DEV`
> is unset in prod. One scope addition beyond the original plan: the two
> QA-flagged mass-mutations (`/companies/regen-all`, `/companies/trader/refresh-all`)
> are now permission-gated (`tasks:action`) so the demoted service token can't
> fire them — the demotion is otherwise toothless for the most destructive ops.
> A full RBAC sweep of the other ~75 ungated mutation routes is deferred to Phase 2.

**Order within this phase is load-bearing: 0.1 must land before 0.2/0.4, or removing the token opens the API (see R3c).**

### 0.1 Make `require_api_token` fail closed
- **Change:** In `server/api.py:337-339`, replace the unconditional dev bypass with an explicit opt-in:
  ```python
  if not expected and presented is None:
      if os.environ.get("BSH_ALLOW_ANON_DEV") == "1":
          return
      # fall through to the 401 below
  ```
  Add `BSH_ALLOW_ANON_DEV=1` to the local `.env` so dev workflows don't break; document in README that it must never be set in prod.
- **Files:** `server/api.py`, `.env`, `README.md`.
- **Tests:** New `tests/test_api_auth.py`: (a) no env token + no credentials + no flag → 401 on `/api/companies`; (b) flag set → 200; (c) valid session token → 200; (d) garbage bearer → 401.
- **Done when:** the test matrix passes and a tokenless curl against a flagless server gets 401 on every `/api/*` route.

### 0.2 Stop injecting the token into HTML
- **Change:** Delete the token-meta block at `server/main.py:308-315` (keep `bsh-research-api-base`, `main.py:316-319` — the `/research` base path needs it). In `frontend/src/api.js:69-75`, delete the `document.querySelector('meta[name="bsh-research-api-token"]')` fallback in `getApiToken()` — session token only.
- **Consumer check:** `docs/ios-app-implementation.md` describes an iOS client; if it scrapes the meta tag, it must move to the login flow (0.4's service token is the alternative). Verify before shipping.
- **Files:** `server/main.py`, `frontend/src/api.js`.
- **Tests:** extend `tests/test_api_auth.py`: fetch `/` and assert `bsh-research-api-token` does not appear in the body even when the env token is set.
- **Done when:** view-source on the deployed page contains no token, and login → browse still works.

### 0.3 Cookie sessions (kills the `?token=` query-param leak)
- **Change:** three coordinated edits:
  1. `POST /api/auth/token` (`api.py:390-408`): after `auth_store.issue_session` (`auth_store.py:253`), also `response.set_cookie("bsh_session", token, httponly=True, secure=True, samesite="lax", path="/research", max_age=30*86400)`. Logout endpoint clears it.
  2. `require_api_token` (`api.py:327`): read `request.cookies.get("bsh_session")` as an additional credential source, validated through the existing `auth_store.validate_token`.
  3. Delete the query-param channel: remove `withApiToken`'s token appending (`api.js:76-82`) and the `token: str | None = Query(...)` param (`api.py:329`). The 13 `withApiToken` call sites (download `<a href>`s in `CompanyLibrary.vue:346-366`, `UnifiedDocumentsView.vue:164`, `ResearchView.vue:235-1018`; `EventSource` in `JobLogModal.vue:250`, `HormuzConsole.vue:164,205`, `TraderView.vue:185`) all become plain same-origin URLs — cookies ride along automatically. Keep `withApiToken` as a passthrough to `withBase` so call sites don't need touching, or inline it.
- **CSRF:** once cookies carry auth, add a cheap guard for mutations: require a custom header (`X-BSH-Client: web`) on non-GET routes, set unconditionally in `apiFetch`. Same-origin `fetch` can set it; a cross-site form cannot.
- **Files:** `server/api.py`, `server/main.py` (cookie path must match `root_path="/research"`, `main.py:86` — verify behind the nginx prefix-strip described at `main.py:74-85`), `frontend/src/api.js`.
- **Tests:** pytest: login sets the cookie; cookie-only request passes auth; non-GET without the header → 403. Manual: a report DOCX download and the job-log SSE stream both work with no `?token=` anywhere (check the Network tab).
- **Done when:** `grep -rn "token=" frontend/src` shows no query-param auth, and nginx access logs stop accumulating credentials.

### 0.4 Rotate the token; demote `shared_auth`
- **Change:** In `server/product_store.py:84-86`, change `shared_auth → "admin"` to a new limited `"service"` role (or delete the branch if nothing legitimately uses the shared token). The three `shared_auth=` call sites are `api.py:850,866,881`. Then rotate `BSH_RESEARCH_API_TOKEN` in the prod environment to a long random secret (or unset it entirely now that 0.1 fails closed) — **ops action, coordinate with whoever owns the box**. Treat `BSH-8688` as burned regardless.
- **Done when:** `BSH-8688` gets 401 in prod, and `/api/auth/me` with any shared token reports a non-admin role.

### 0.5 Seed passwords + login rate limiting
- **Change:** Remove the plaintext seed list at `server/auth_store.py:42-53`. Replace with: seed emails only, passwords set via a one-time `BSH_BOOTSTRAP_PASSWORD` env or a CLI (`python -m server.auth_store set-password <email>`), and a `must_reset` flag honored by the login flow. Invalidate all existing sessions (bump a session-version salt or truncate the sessions file) since `redapple` is in git history. Add rate limiting to `login` (`api.py:390`): in-memory counter, 5 failures per email per 15 min → 429.
- **Files:** `server/auth_store.py`, `server/api.py`, `scripts/` (password CLI).
- **Tests:** pytest: 6th bad login → 429; `redapple` rejected after reseed.
- **Done when:** every real account has a fresh password and the old sessions are dead.

**Phase 0 exit check:** full pytest + manual matrix (anon / bad token / session / cookie) against a staging run of `./run.sh`.

---

## Phase 1 — Performance & memo reliability

> **Status: DONE (2026-07-14).** Implemented on `main`. Backend 400 pass / 1
> pre-existing flake; frontend 120 pass, lint clean, build OK. **Live latency on
> real data:** autocomplete ~5 ms (was ~7 s), `/api/reports` 22 ms (was
> hanging), `/api/companies` 21 ms, `/api/jobs/active` 24 ms→1.3 ms on cached
> hits. `list_companies` 1253 ms→12 ms, `get_company` 1246 ms→0.4 ms,
> `list_reports` 114 ms→1.6 ms. The storage cache also cut the test suite from
> 108 s to 66 s. New tests: `tests/test_storage_cache.py`,
> `tests/test_memo_package_timeouts.py`. Deferred within this phase: `/api/reports`
> pagination/ETag (unneeded once cached), the `content_block_delta` liveness
> refinement for the silence guard (1.1 follow-up), and splitting
> `trader_snapshot`/`translation` out of `companies.yaml` (that's Phase 3.4).

Biggest user-visible win per line changed. 1.1 is independent of everything else — it can ship same-day.

### 1.1 Memo silence timeouts (the one-line fix, ×2)
- **Change:** Introduce `MEMO_PACKAGE_SILENCE_TIMEOUT_SEC = 600` in `server/claude_runner.py` and use it in all three package passes:
  - the bilingual pass — add `silence_timeout_sec=MEMO_PACKAGE_SILENCE_TIMEOUT_SEC` to the `_run_memo_json_claude` call inside `run_memo_fast_bilingual_package` (currently omitted → inherits 180 from `:3345`);
  - the resume pass — replace the hardcoded `silence_timeout_sec=180` at `claude_runner.py:4326` (matches the 2 "memo package resume stalled" failures);
  - the English pass at `:3635` already passes 600 — switch it to the constant for consistency.
- **Tests:** unit test asserting the constant is threaded through (monkeypatch `_consume_stream_json_process`, capture kwargs). An end-to-end memo run is the real proof but takes ~30 min — do one after deploy, not in CI.
- **Done when:** a fresh memo generation for a real company completes without a "stalled after 180s" error. This addresses 8 of the 9 hard failures on record.
- **Follow-up (separate PR):** make the silence guard count `content_block_delta` traffic as liveness in `_consume_stream_json_process` (`:1490`), so it measures true stalls instead of "no complete event yet."

### 1.2 Memoize the companies file
- **Change:** In `server/storage.py`, add a module-level cache keyed on `COMPANIES_FILE.stat()` → `(st_mtime_ns, st_size)`:
  ```python
  _COMPANIES_CACHE: tuple[tuple[int, int], list[dict]] | None = None
  ```
  `list_companies()` checks the stat key and returns `copy.deepcopy(cached_list)` on hit; `_write_yaml` to `COMPANIES_FILE` (and `upsert_company_from_match` / `update_company`) invalidates. **Return a deepcopy, not the cached objects** — several callers mutate what they get back (e.g. `upsert_company_from_match` edits records in place before writing). Deepcopy of the current 1.24 MB structure costs ~100-200 ms — still 6-10× better than the 1253 ms parse, and it drops to ~0 once 3.4 shrinks the file.
  Also add a cached `{id: record}` index so `get_company()` (`storage.py:103-107`) stops linear-scanning a full parse.
- **Files:** `server/storage.py` only.
- **Tests:** new `tests/test_storage_cache.py`: cache hit returns equal data; `upsert_company_from_match` then `list_companies` reflects the write; mutation of a returned record does not leak into a subsequent call. Existing `test_storage_company_type.py` must pass untouched.
- **Done when:** `python -c` benchmark shows warm `list_companies()` under 200 ms (vs 1253 ms) and warm `get_company()` under 10 ms.

### 1.3 Hoist `get_company()` out of the jobs loops
- **Change:** At `api.py:3680`, `:4028`, `:4354`, replace per-job `storage.get_company(cid)` with one `{c["id"]: c.get("name")}` map built per request from `list_companies()` (cheap after 1.2).
- **Done when:** `/api/jobs/active` makes exactly one companies read per request regardless of job count.

### 1.4 Tame the polling storm
- **Change:**
  1. `App.vue:24-45` — add the in-flight guard `refreshAll` is missing (mirror `ActiveJobsRail.vue:33`): `let refreshing = false; if (refreshing) return; …`.
  2. `App.vue:26` — `Promise.all` → `Promise.allSettled`, assigning each fulfilled result individually so one failed endpoint can't blank the sidebar.
  3. Pause on `document.hidden` (listen for `visibilitychange`; skip ticks while hidden, refresh once on return).
  4. Raise the sidebar interval from 4 s to 20 s — it feeds a nav list, not a live view; the `@reports-changed` event (`App.vue:259`) already covers the "I just created something" case with an immediate refresh.
  5. Consolidate the three `/api/jobs/active` pollers (`ActiveJobsRail.vue:66` @3s, `ResearchUploads.vue:241` @2s, `WeeklySummaryView.vue:218`) into one shared module — new `frontend/src/activeJobs.js` exporting a reactive `jobs` ref plus `subscribe()/unsubscribe()` that reference-count a single 5 s interval. The three components consume the ref instead of owning timers.
- **Files:** `frontend/src/App.vue`, new `frontend/src/activeJobs.js`, `ActiveJobsRail.vue`, `ResearchUploads.vue`, `WeeklySummaryView.vue`.
- **Tests:** existing `AppShell.spec.js`, `ActiveJobsRail.spec.js`, `HomeView.spec.js` must pass; add a vitest for `activeJobs.js` (single timer across two subscribers; timer cleared at zero).
- **Done when:** DevTools Network on an idle Home page shows ≤ 4 requests per 20 s (was ~80/min), and none stack while a slow response is in flight.

### 1.5 Get recovery sweeps off the `/api/jobs/active` request path
- **Change:** Move the three `recover_stale_runs` calls (`api.py:4440-4453` — serena, research jobs, stock research) out of `get_active_jobs` into (a) the startup hook (`main.py:118`) and (b) a background thread ticking every 5 min. Then wrap the remaining aggregation (the 17 glob generators, `api.py:4455-4473`) in a 3 s TTL cache so concurrent pollers share one scan.
- **Files:** `server/api.py`, `server/main.py`.
- **Tests:** pytest with a monkeypatched call-counter proving `get_active_jobs` no longer invokes any `recover_*`; recovery covered by a direct call test.
- **Done when:** p95 latency of `/api/jobs/active` under three concurrent pollers is < 250 ms, and the prod 503s stop. Then close the loop on the report's [High]: check the prod uvicorn flags / nginx `error_log` to confirm which layer was emitting 503 (the app provably never does — see R3 notes).

### 1.6 `/api/reports` cache
- **Change:** In `storage.list_reports()` (`storage.py:386-396`), cache each parsed report YAML keyed on its file's `(mtime_ns, size)` — stat-ing 48 files is microseconds; re-parse only changed ones. Defer pagination/ETag (stretch — the list is small once parses are cached; the hang was lock starvation, fixed by 1.2/1.5).
- **Done when:** warm `/api/reports` < 50 ms.

### 1.7 Autocomplete off the floor
- **Change:** in `server/companies_autocomplete.py`:
  1. Prefetch the EDGAR index in the startup hook (background thread — don't block boot); stop holding `_INDEX_LOCK` across the 8 s `httpx` fetch (`:46-51`): fetch outside, swap under the lock.
  2. Build the "researched" index once at startup and refresh in a background thread every 60 s; delete the on-request 30 s TTL rescan (`:123, :130-177`).
  3. Local matches come via `storage.search_companies` — already fast after 1.2.
- **Tests:** extend `tests/test_companies_autocomplete.py`; assert `autocomplete()` never triggers a network fetch when the index is warm (monkeypatch httpx).
- **Done when:** warm autocomplete round-trip < 300 ms server-side (was ~7 s perceived).

### 1.8 Sidebar loading flash
- **Change:** `Sidebar.vue:188` — render the count only when settled: `<span v-if="!loading || companies.length">…</span>`, em-dash otherwise. (1.4's `allSettled` fixes the related blank-on-error; 1.2 collapses the flash window to a single frame.)
- **Done when:** hard reload shows skeleton → 73, never "0".

**Phase 1 exit check:** pytest + vitest green; manual: Home cold load, type "Apple" (fast dropdown), Network tab quiet at idle; one full memo generation completes end-to-end.

---

## Phase 2 — Correctness (company identity + memo durability)

*(Anchors re-verified 2026-07-14 after Phases 0–1 shifted line numbers. Prefer the
symbol names; line numbers are hints.)*

### 2.1 Company identity: match on evidence, not prose
- **Where:** `storage.upsert_company_from_match` (`server/storage.py:348`) — the only
  company-creation path. Its match loop keys on ticker equality, then exact
  normalized-name equality; `website`/`logo_domain` are collected into `enrichment`
  but never used as match keys; `"aliases": []` is hardcoded on create (`storage.py:~435`).
- **Change:** rework the match loop in this priority order:
  1. ticker equality (both non-null) — existing;
  2. **new:** normalized `website` host or `logo_domain` equality (strip `www.`, lowercase);
  3. normalized-name equality — **but only between records of the same public/private standing:** a tickerless candidate must never merge into a tickered record (this is the guard that saves `goog` — R5d);
  4. alias match (see below).
  And gate the *merge*: if both sides have a website/logo_domain and the hosts disagree, treat as a different company (create, don't enrich) even on a name hit.
- **Normalization fixes:** `_LEGAL_SUFFIX_RE` (`storage.py:298`) is anchored to `$`, so a trailing parenthetical (`…, Inc. (AMI Labs)`) defeats it — strip suffix tokens positionally; strip parenthetical segments in `_normalize_company_name` (`storage.py:328`) before comparing; on create, put the parenthetical into `aliases` and include aliases in the match loop.
- **Cache note:** mutations inside `upsert_company_from_match` operate on the deepcopy that `list_companies()` returns and persist via `_write_yaml` — that bumps mtime and self-invalidates the Phase 1 cache. Keep that pattern; don't cache-poke directly.
- **Tests:** new `tests/test_company_dedup.py`, seeded with the three real-world regressions:
  - the three AMI name variants (`Advanced Machine Intelligence Labs (AMI Labs)` / `Advanced Machine Intelligence, Inc. (AMI Labs)` / `Advanced Machine Intelligence Labs, Inc.`, all `website: ami.xyz`) upsert to **one** record;
  - a `{name: "Alphabet Inc.", website: alphabetsigns.com, ticker: null}` candidate does **not** touch `goog` — it creates a separate record;
  - `{ticker: GOOG}` candidate still enriches `goog`.
- **Done when:** that suite passes and `test_company_seed_data.py` / `test_storage_company_type.py` / `test_storage_cache.py` stay green.

### 2.2 Refresh must never mint a sibling
- **Where:** `_refresh_company_summary` (`server/api.py:1966`); the smoking-gun fallback `chosen = matches[0]` is at `api.py:1986`. `companies_ai.deep_search` (`server/companies_ai.py:236`) upserts **every** returned match.
- **Change:** delete the `matches[0]` fallback — when no returned match has `id == company_id`, log and abort the refresh (or surface "refresh returned a different company"). Query `deep_search` by the stable key — `ticker or website host or name` — rather than the mutable AI `name` alone. Additionally, on the refresh path have `deep_search` upsert **only the chosen match**, not every match in the response.
- **Schema follow-up (same PR if cheap, else Phase 4.5):** add `legal_name` + `disambiguator` to `SCHEMA` in `companies_ai.py` and tell `SYSTEM_PROMPT` (`companies_ai.py:195`) to put "Dallas, TX" there; derive the slug from `legal_name`. This removes the incentive that fabricated `Alphabet Inc. (Dallas, TX)`.
- **Tests:** pytest with a faked `deep_search` returning a mismatched id → assert no new record and no overwrite. (Pattern reference: `test_regen_all_*` in `tests/test_trader_snapshot.py` fakes `deep_search` already.)
- **Done when:** refreshing any company N times changes the record count by 0.

### 2.3 Memo durability: orphans, resume, and the poll loop
- **Change:**
  1. **Demote orphans.** In `recover_stale_reports` (`server/memo_analysis.py:2833`), the `if not result: continue` branch (`:2863`, reading `stream_state["success_result"]`) abandons restart-killed runs at `analyzing/15` forever. Add: if a report is `analyzing` and its `stream.jsonl` mtime is older than a threshold (30 min) with no terminal event and no live worker thread, transition it to `failed_during_analysis` with `error: "orphaned by server restart"` — which makes it eligible for the existing resume path (resume requires `status.startswith("failed")`, see `api.py:2294` and `:2458`).
  2. **Die loudly.** Register an `atexit` handler (and SIGTERM handler) that writes a terminal `error` event for any in-flight memo runs, so a clean restart doesn't even need the sweep. Keep `daemon=True` in `start_analysis` (`memo_analysis.py:2963`) — a supervised worker is Phase 4.6; demote+atexit covers the observed failure mode.
  3. **Fix the poll loop.** `frontend/src/views/ResearchView.vue` — `pollReport()` (`:469`) calls `stopPolling()` unconditionally in its `catch` (`:488`); polling is 1/s for 30+ min, so one blip freezes the UI forever. Replace with a consecutive-failure counter: reset on success, back off 1s→2s→5s, give up only after 5 straight failures and show a "connection lost — retry" affordance.
  4. **UX for a 30-minute job.** Surface the per-phase progress the backend already emits (`phase_timing` events, `_emit_phase_timing` at `memo_analysis.py:135`): phase name + elapsed + rough ETA + "safe to close this tab". This turns "never completes" into "in progress, phase 3/5, ~12 min left".
- **Deferred to Phase 4:** migrating the memo UI onto the existing SSE stream (`GET /api/memos/{report_id}/stream`, `api.py:2527`, currently consumed by nothing — note: EventSource now authenticates via the Phase 0 session cookie, so this migration got easier). Same for parallelizing the bilingual pass (R6d).
- **Tests:** pytest for the demote logic (fixture report dir with a stale stream.jsonl → status flips, resume-eligible); `test_memo_analysis.py` stays green. Vitest for the retry counter.
- **Done when:** kill -9 the server mid-generation, restart → within one sweep the run shows `failed_during_analysis` with a working Resume button; and a transient 500 during polling no longer freezes the progress UI.
- **Data cleanup rider:** after the demote logic lands, run it against prod data to clear the 12 stuck `analyzing` reports.

### 2.4 One canonical category
- **Change:** Add `"category": company.get("industry") or company.get("sector")` to `_company_view()` (`server/api.py:6661`) and to the autocomplete/search result shaping (`server/companies_autocomplete.py` emits `sector`/`industry` on researched hits; local hits come from `storage.search_companies`); switch the five render sites (`HomeView.vue:425` search typeahead, `CompanyCard.vue:88`, `ResearchView.vue:~688` detail header, `CompanyDetail.vue:~190`, `Sidebar.vue:~225`) to `company.category`. Detail pages may additionally show `sector · industry` labeled.
- **Deferred to Phase 4.5:** GICS `enum` on `sector` in the AI schema + backfill; the user-visible inconsistency is fixed by the display contract alone.
- **Done when:** Apple (`aapl`: `sector: Technology`, `industry: Consumer Electronics`) shows the same category string in search, card, sidebar, and detail.

**Phase 2 exit check:** dedup suite green; refresh-idempotence verified on 3 companies in staging; kill/restart memo drill passes; full pytest (expect the known flake only) + vitest.

---

## Phase 3 — Product polish + regression guards

### 3.1 Wire `?intake=` (fixes two reported bugs at once)
- **Change:**
  1. Each tool (`SubmitLinkTool.vue:20`, `UploadResearchTool.vue:19`, `AddHormuzResearchTool.vue:21`) — replace `const expanded = ref(false)` with `const expanded = defineModel("expanded", { default: false })`. Their own header toggles keep working through the model.
  2. `HomeView.vue` — add `useRoute()`; three refs; bind `v-model:expanded` at `:456-458`; and:
     ```js
     watch(() => route.query.intake, (v) => {
       linkOpen.value = v === "link";
       uploadOpen.value = v === "upload";
       noteOpen.value = v === "note";
       if (v) nextTick(() => quickAddEl.value?.scrollIntoView({ behavior: "smooth" }));
     }, { immediate: true });
     ```
  3. Sidebar links (`Sidebar.vue:161-181`) need no change — they already emit the right URLs. Note: clicking the *same* sidebar button twice is a same-route navigation (no-op); acceptable, or append a nonce to the query if re-open-on-reclick matters.
- **Tests:** vitest in `HomeView.spec.js`: mount with router at `/?intake=link` → SubmitLinkTool form visible; at `/?intake=upload` → upload form visible.
- **Done when:** all three sidebar buttons and all three deep-link URLs from the QA report open the right form.

### 3.2 Submit-link validation + upload title
- **Change (SubmitLinkTool.vue):** input `type="url"` → `type="text"` (`:100`) so native validation stops silently cancelling submit; drop `!url.trim()` from the button's `:disabled` (`:106`, keep `previewing`); in `runPreview` (`:43`), replace the silent `return` with `error.value = t("submit_link.error_url_required")`, and validate with `new URL(u.startsWith("http") ? u : "https://" + u)` in a try/catch → `error.value = t("submit_link.error_url_invalid")` (mirrors the server's own https-prefixing at `api.py:4705`). Apply the same guard to `accept()` (`:54`). Add the two keys to both i18n blocks.
- **Change (UploadResearchTool.vue):** delete line 37 (`if (!title.value) title.value = f.name…`). The placeholder already says "Title (defaults to filename)" and the server already defaults it (`api.py:5537`).
- **Tests:** new `frontend/tests/SubmitLinkTool.spec.js`: empty submit → error rendered; `not-a-real-url-xyz` → error rendered, no fetch; valid URL → `api.linkPreview` called. Upload spec: after picking a file, title stays empty and typing produces only the typed text.
- **Done when:** the QA repro steps produce visible feedback.

### 3.3 i18n: keys, call sites, and the lint that keeps it fixed
- **Change,** in three moves:
  1. **Keys:** add ~40 keys to both `en` and `zh` blocks of `i18n.js` (inventory in R7): `sidebar.quick_intake`, `.submit_link`, `.upload_research`, `.add_internal_note`, `.companies`, `.bucket_portfolio/_pipeline/_top_players`, `.no_companies`, `.show_less/.show_all`, `.market_radar`, `.stock/.stock_hint`, `.innovation_lab`, `.settings`, `.profile`; `home.operations/.operations_hint`; `nav.*` breadcrumbs; `news.*` (~16 for the Company News panel); `submit_link.error_*` (from 3.2). Reuse existing keys where present (`research.tab_news`, `home.tag_tracked`, `sidebar.untitled`, `sidebar.external_source`).
  2. **Call sites:** `Sidebar.vue` (:95-97 — keep inside the `computed` for reactivity — plus :159-313), `HomeView.vue:596-598`, `App.vue` (import `useT`; key `tabLabel()` :93-100 as `t("research.tab_" + tab)` and the breadcrumb table :102-137, :201), `ResearchView.vue:1286-1408` (all 16 news-panel strings, including `placeholder=` and `aria-label=` attrs).
  3. **Server:** `context_store.py:219` — return an empty `empty_state` (client renders `t("news.empty")`); add `lang` query param to `GET /api/companies/{id}/news-feed` (`api.py:2906`) plumbed from `api.js:184-191`, and have `company_news()` (`context_store.py:180`) prefer `company["translation"]["recent_news"]` when `lang=zh` — the translations already exist (`company_translate.py:206-209`); they're just never read. External-archive items have no zh source — out of scope, note in code.
- **The regression guard (the point of this task):** extend `frontend/tests/i18n.spec.js` with (a) a global every-`en`-key-has-a-`zh`-key assertion, and (b) a template scan: parse `src/**/*.vue` `<template>` blocks and fail on bare text nodes or `placeholder=`/`aria-label=`/`title=` literals matching `[A-Za-z]{3,}` outside `{{ t(…) }}`, with an allowlist (`Berkeley Summit House`, `BSH`, tickers, `·`). Wire it so the ~60 current violations must be fixed for CI to pass — that's what proves the sweep is complete.
- **Done when:** the hardened i18n spec passes, and toggling 中 leaves no English in the sidebar, header, Operations block, or Company News chrome; news *content* renders Chinese for companies with translations.

### 3.4 Split the fat out of `companies.yaml`
- **Change:** Move `trader_snapshot` (864 KB) and `translation` (327 KB) — already flagged as locally-generated in `_LOCAL_GENERATED_COMPANY_FIELDS` near the top of `storage.py` — to per-company sidecar files `data/company_ext/<id>.yaml`. `storage.py` grows `get_company_ext(id)` / `set_company_ext(id, field, value)`; `update_company_snapshot` and the translation writer redirect to sidecars; `migrate_trader_snapshots` reads sidecars. `_company_view()` (`api.py:6661`) loads sidecars lazily only for detail endpoints — list endpoints (`/api/companies`) omit both fields entirely. One-time migration inside `local_generation.generate_local_runtime_state()` (idempotent: hoist fields out if present, write sidecars, rewrite slim `companies.yaml`).
- **Interplay with the Phase 1 cache:** the mtime-keyed cache in `storage.py` stays exactly as is — a slim `companies.yaml` just makes its cold parse (~1.2s→~10ms) and the per-call deepcopy (~100-200ms→~1ms) nearly free. Sidecars get their own small per-id cache if needed; don't fold them into the main cache key.
- **Blast radius:** grep consumers of `company["trader_snapshot"]` / `["translation"]` across `server/` (`trader_stats.py`, `company_translate.py`, `trader_bilingual_fill.py`, `memo_chinese_parity.py`, `companies_ai_public.py`, …) and route them through the accessor. This is the phase's one genuinely invasive task — do it last, behind green tests.
- **Tests:** migration idempotence; `test_trader_snapshot.py`, `test_company_translation_backfill.py`, `test_trader_stats.py`, `test_storage_cache.py` green; detail endpoints still serve both fields.
- **Done when:** `companies.yaml` < 100 KB, warm `list_companies()` < 5 ms, and `/api/companies` response drops from ~1.2 MB to a few KB.

### 3.5 One-off data cleanup (prod)
- **Change:** a runnable, idempotent script `scripts/qa_2026_07_13_cleanup.py` with `--dry-run` (default) and `--apply`:
  1. Merge the three AMI records into one canonical (`advanced-machine-intelligence-labs-ami-labs` — pick the richest); repoint any reports/uploads/threads/evidence referencing the losers (grep `data/` by id); keep the losing slugs as `aliases`; delete the losers. Requires 2.1 landed first so they can't re-split.
  2. Fix `alphabet-inc-dallas-tx` → rename to `Alphabet Signs` (`name`, slug stays or migrates), keeping its real `alphabetsigns.com` identity.
  3. Delete the three QA test records from the report (internal note "TEST - please delete (QA bug test)", the example.com link item, the `BSH_TEST_please_delete.txt` external report) — all created under seline.sun@bshfoundation.org on 2026-07-13.
  4. Purge the poisoned `companies_ai` cache entries (the four AMI keys + `alphabet inc. (dallas, tx)`).
- **Done when:** `--dry-run` output reviewed by Robert, then `--apply` on prod data; company count drops 73 → 71 and the QA records are gone.

**Phase 3 exit check:** full pytest + vitest + `npm run lint`; manual bilingual walkthrough of the Home page; the three QA deep-links; one upload with a custom title.

---

## Phase 4 — Hardening & deferred work

Everything earlier phases consciously deferred, now actionable. These are independent
of each other — pick by value; 4.1 is the most important.

### 4.1 Full RBAC sweep of mutation routes
- **Why:** only ~15 of ~90 POST/PATCH/PUT/DELETE routes call `_require_permission`.
  Phase 0 gated the two QA-flagged mass-mutations (`/companies/regen-all`,
  `/companies/trader/refresh-all`, both `tasks:action`); the rest are open to any
  authenticated caller — including the read-only `service` role, which makes its
  demotion incomplete.
- **Change:** enumerate every mutation route in `server/api.py`
  (`grep -n '@router\.\(post\|patch\|put\|delete\)' server/api.py`), assign each a
  permission from `product_store.ROLE_PERMISSIONS` (`sources:edit`,
  `documents:delete`, `memo:edit`, `memo:export`, `tasks:action`, `settings:update`
  — add new ones sparingly), and add `_require_permission(request, ...)` at the top
  of each handler (add the `request: Request` param where missing; check nothing
  calls the handler as a plain function first).
- **Watch out:** anon-dev resolves to `admin` (full access — tests rely on this via
  the conftest fixture), so the existing suite should stay green; add
  service-role 403 tests per route group to `tests/test_api_auth.py` following the
  existing `test_shared_token_cannot_fire_mass_mutations` pattern.
- **Done when:** every mutation route enforces a permission and the service token
  gets 403 on all of them.

### 4.2 SSE-based memo progress (replace the 1s poll)
- **Why:** `GET /api/memos/{report_id}/stream` (`api.py:2527`) already exists with a
  correct 600s idle deadline and full replay from `stream.jsonl` — and nothing
  consumes it. Phase 0's session cookie means `EventSource` now authenticates with
  no URL tokens, so the old blocker is gone.
- **Change:** in `ResearchView.vue`, replace the `pollReport` interval with an
  `EventSource` on that stream (pattern reference: `JobLogModal.vue` and
  `HormuzConsole.vue` already use EventSource). Keep the Phase 2.3 bounded-retry
  poll as the fallback if the stream errors.
- **Done when:** a page reload mid-generation restores full progress history and
  the Network tab shows one open stream instead of 1/s polls.

### 4.3 Silence-guard liveness refinement
- **Why:** Phase 1.1 raised the package passes to 600s, but the guard in
  `_consume_stream_json_process` (`claude_runner.py`, `last_event_at`) still only
  counts whole stream-json events — a legitimately long single generation can
  still trip it.
- **Change:** treat partial `content_block_delta` traffic as liveness so the guard
  measures true stalls. Keep `MEMO_PACKAGE_SILENCE_TIMEOUT_SEC` as the ceiling.

### 4.4 Parallelize the bilingual memo pass
- **Why:** phases 3 (English package) and 4 (bilingual) are strictly serial;
  worst-case memo budget ≈ 90 min (R6d). The bilingual pass is a pure translation
  of phase 3's output.
- **Change:** split the package per-section and fan out across the existing
  `ThreadPoolExecutor` (`BSH_MEMO_FAST_MAX_WORKERS`, default 4, in
  `memo_analysis.py`), or overlap section-wise with English synthesis. Verify the
  Chinese-parity gate (`memo_chinese_parity.py`) still passes on reassembled output.

### 4.5 Company schema hardening (`legal_name`/`disambiguator`, GICS enum)
- **Why:** completes 2.2/2.4 — removes the prompt incentive to smuggle "Dallas, TX"
  into `name`, and stops `sector` oscillating between taxonomies
  (`aapl: Technology` vs `goog: Communication Services`).
- **Change:** extend `SCHEMA` + `SYSTEM_PROMPT` in `companies_ai.py`; derive slugs
  from `legal_name`; constrain `sector` to a GICS enum; one-off backfill pass over
  `data/companies.yaml` records.

### 4.6 Supervised memo worker
- **Why:** Phase 2.3's atexit + orphan-demotion covers observed failures, but a
  bare `daemon=True` thread (`memo_analysis.start_analysis`) still dies silently
  with the process.
- **Change:** move memo generation to a supervised worker (process pool or a
  restart-surviving queue) so an uvicorn restart resumes rather than orphans runs.

### 4.7 Server-side translation of external-archive news
- **Why:** Phase 3.3 wires zh for `recent_news` (translations already exist on the
  company record) — but external-archive items (`external_store.list_items("news")`)
  have no zh source at all. `external_translate.py` only handles research PDFs.
- **Change:** add a translate pass for news items (mirror
  `company_translate.translate_company`), cache per item, serve via the `lang=zh`
  param added in 3.3.

### 4.8 Fix the pre-existing flaky test
- `tests/test_trader_snapshot.py::test_regen_all_proactively_backs_off_at_usage_window_guard`
  fails on baseline `main` (verified 2026-07-14 via git stash; see auto-memory).
  It expects a `stage/backing_off` event with `backoff_kind ==
  "proactive_usage_window"` that the regen pipeline doesn't emit. Root-cause the
  backoff heuristic in the regen-all path (`server/api.py` around
  `_tracked_companies_for_regen` / usage-window guard) as its own task.

### 4.9 Ops checklist (user-owned; blocked on box access)
- Rotate `BSH_RESEARCH_API_TOKEN` in prod — `BSH-8688` is burned. Or leave unset
  (auth now fails closed).
- Set real passwords for all seed accounts (`python -m server.auth_store
  set-password <email>`), then `revoke-all` — `redapple` is in git history.
- Confirm `BSH_ALLOW_ANON_DEV` is unset in prod.
- Confirm which front layer emitted the 503s (uvicorn `--limit-concurrency` in the
  prod launch command / nginx `limit_req` + `error_log`) — the app never emits 503
  for `/api/*`; Phase 1.5 removed the overload that triggered it either way.
- `/api/reports` pagination + ETag/304: intentionally dropped — the list is cheap
  once cached; starvation was the real cause. Revisit only if report count grows
  10×.

---

## Notes on the report itself

The QA was good — the console really is clean, and every issue filed is real. Three corrections for the record:

- **"Sidebar re-fetching on every render"** — no; `Sidebar.vue` mounts once and is prop-driven. It is four `setInterval` timers.
- **"/api/jobs/active returns 503 (server-side)"** — correct that it is server-side, but **the app never emits 503**. It comes from uvicorn's concurrency limiter or nginx, because the app is being overloaded by its own polling. Confirm the prod `--limit-concurrency` / nginx `error_log`.
- **Memo generation "never completes"** — it completes in ~30 minutes when it works, and it has a 40% success rate. Both halves need fixing, and the UX half (no ETA on a half-hour job) is why the tester couldn't tell.
