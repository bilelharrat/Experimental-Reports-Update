"""One-off data cleanup for the 2026-07-13 QA bug report (plan §3.5).

Actions (idempotent — reruns are no-ops):
  1. Merge the three AMI company records into the canonical
     ``advanced-machine-intelligence-labs-ami-labs`` (richest record),
     keeping losing names/slugs as aliases, merging sidecar ext fields,
     and repointing any ``data/`` file that references a losing id.
  2. Rename ``alphabet-inc-dallas-tx`` to "Alphabet Signs" — it is really
     Alphabet Signs of Dallas (alphabetsigns.com); the model fabricated the
     legal-sounding name (see remediation plan R5d).
  3. Delete the three QA test records the report asked to remove.
  4. Purge the poisoned ``companies_ai`` cache entries (AI-generated name
     variants that were replayed as queries — R5c).

Usage:
    python -m scripts.qa_2026_07_13_cleanup            # dry-run (default)
    python -m scripts.qa_2026_07_13_cleanup --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import cache, external_store, storage  # noqa: E402

CANONICAL_AMI = "advanced-machine-intelligence-labs-ami-labs"
AMI_LOSERS = [
    "advanced-machine-intelligence-inc-ami-labs",
    "advanced-machine-intelligence-labs-inc",
]

ALPHABET_ID = "alphabet-inc-dallas-tx"
ALPHABET_NEW_NAME = "Alphabet Signs"

# (kind, item_id, human label) — from the QA report, all created by
# seline.sun@bshfoundation.org on 2026-07-13.
QA_TEST_RECORDS = [
    ("hormuz_research", "2f002bf221ef", 'internal note "TEST - please delete (QA bug test)"'),
    ("news", "0d29a4cbffd2", "example.com link submission"),
    ("external_research", "d9caef426851", "BSH_TEST_please_delete.txt upload"),
]

POISONED_CACHE_KEYS = [
    "ami labs",
    "advanced machine intelligence labs (ami labs)",
    "advanced machine intelligence, inc. (ami labs)",
    "advanced machine intelligence labs, inc.",
    "alphabet inc. (dallas, tx)",
]

# Fields that never merge across records (identity/bookkeeping).
_NO_MERGE_FIELDS = {"id", "name", "aliases"}


def _log(msg: str) -> None:
    print(msg)


def _merge_missing(canonical: dict, loser: dict) -> list[str]:
    """Copy loser fields the canonical record lacks. Returns copied keys."""
    copied = []
    for k, v in loser.items():
        if k in _NO_MERGE_FIELDS:
            continue
        if not storage._has_value(canonical.get(k)) and storage._has_value(v):
            canonical[k] = v
            copied.append(k)
    return copied


def _data_files_referencing(data_dir: Path, needle: str) -> list[Path]:
    hits = []
    for path in data_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".yaml", ".yml", ".json", ".jsonl", ".md"}:
            continue
        # companies.yaml itself is handled structurally, not textually.
        if path == storage.COMPANIES_FILE:
            continue
        try:
            if needle in path.read_text(encoding="utf-8"):
                hits.append(path)
        except (UnicodeDecodeError, OSError):
            continue
    return hits


def merge_ami(apply: bool) -> None:
    canonical = storage.get_company(CANONICAL_AMI)
    if canonical is None:
        _log(f"[ami] canonical {CANONICAL_AMI} not found — skipping (already cleaned?)")
        return
    losers = [(lid, storage.get_company(lid)) for lid in AMI_LOSERS]
    losers = [(lid, rec) for lid, rec in losers if rec is not None]
    if not losers:
        _log("[ami] no loser records found — nothing to merge")
        return

    companies = storage.list_companies()
    by_id = {c.get("id"): c for c in companies}
    canon_rec = by_id[CANONICAL_AMI]
    aliases = list(canon_rec.get("aliases") or [])
    existing_keys = storage._company_name_keys(canon_rec)

    for lid, loser in losers:
        _log(f"[ami] merging {lid} ({loser.get('name')!r}) into {CANONICAL_AMI}")
        copied = _merge_missing(canon_rec, {k: v for k, v in loser.items()
                                            if k not in storage.COMPANY_EXT_FIELDS})
        if copied:
            _log(f"[ami]   fields copied: {', '.join(sorted(copied))}")
        for alias in [loser.get("name"), lid, *(loser.get("aliases") or [])]:
            norm = storage._normalize_company_name(str(alias or ""))
            if alias and norm and norm not in existing_keys:
                aliases.append(str(alias))
                existing_keys.add(norm)
        # Sidecar ext fields (trader_snapshot/translation): keep canonical's,
        # adopt the loser's only where canonical has none.
        loser_ext = storage.get_company_ext(lid)
        canon_ext = storage.get_company_ext(CANONICAL_AMI)
        for field in storage.COMPANY_EXT_FIELDS:
            if storage._has_value(loser_ext.get(field)) and not storage._has_value(
                canon_ext.get(field)
            ):
                _log(f"[ami]   adopting sidecar field {field} from {lid}")
                if apply:
                    storage.set_company_ext(CANONICAL_AMI, field, loser_ext[field])
        refs = _data_files_referencing(storage.DATA_DIR, lid)
        for path in refs:
            _log(f"[ami]   repointing reference in {path}")
            if apply:
                text = path.read_text(encoding="utf-8")
                path.write_text(text.replace(lid, CANONICAL_AMI), encoding="utf-8")
        ext_path = storage._company_ext_path(lid)
        if ext_path.exists():
            _log(f"[ami]   deleting sidecar {ext_path}")
            if apply:
                ext_path.unlink()

    canon_rec["aliases"] = aliases
    loser_ids = {lid for lid, _ in losers}
    slimmed = [c for c in companies if c.get("id") not in loser_ids]
    for i, c in enumerate(slimmed):
        if c.get("id") == CANONICAL_AMI:
            slimmed[i] = canon_rec
    _log(f"[ami] company count {len(companies)} -> {len(slimmed)}; "
         f"canonical aliases: {aliases}")
    if apply:
        storage._write_yaml(storage.COMPANIES_FILE, slimmed)


def rename_alphabet(apply: bool) -> None:
    rec = storage.get_company(ALPHABET_ID)
    if rec is None:
        _log(f"[alphabet] {ALPHABET_ID} not found — skipping")
        return
    if rec.get("name") == ALPHABET_NEW_NAME:
        _log(f"[alphabet] already renamed to {ALPHABET_NEW_NAME!r}")
        return
    old = rec.get("name")
    aliases = list(rec.get("aliases") or [])
    if old and old not in aliases:
        aliases.append(old)
    _log(f"[alphabet] renaming {ALPHABET_ID}: {old!r} -> {ALPHABET_NEW_NAME!r} "
         f"(old name kept as alias)")
    if apply:
        storage.update_company(ALPHABET_ID, name=ALPHABET_NEW_NAME, aliases=aliases)


def delete_qa_records(apply: bool) -> None:
    for kind, item_id, label in QA_TEST_RECORDS:
        try:
            item = external_store.get_item(kind, item_id)
        except Exception:
            item = None
        if not item:
            _log(f"[qa] {kind}/{item_id} ({label}) already gone")
            continue
        _log(f"[qa] deleting {kind}/{item_id}: {label} "
             f"(title={item.get('title')!r})")
        if apply:
            external_store.delete_item(kind, item_id)


def purge_cache(apply: bool) -> None:
    for key in POISONED_CACHE_KEYS:
        entry = cache.get("companies_ai", key)
        if entry is None:
            _log(f"[cache] {key!r} not present")
            continue
        _log(f"[cache] purging companies_ai entry {key!r}")
        if apply:
            cache.invalidate("companies_ai", key)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes. Without this flag the script only prints what it would do.",
    )
    args = parser.parse_args()
    mode = "APPLY" if args.apply else "DRY-RUN"
    _log(f"=== QA 2026-07-13 cleanup ({mode}) ===")
    merge_ami(args.apply)
    rename_alphabet(args.apply)
    delete_qa_records(args.apply)
    purge_cache(args.apply)
    if not args.apply:
        _log("Dry-run only. Re-run with --apply to write changes.")


if __name__ == "__main__":
    main()
