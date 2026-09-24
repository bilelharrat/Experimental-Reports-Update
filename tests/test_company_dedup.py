"""Company identity: upsert_company_from_match must key on evidence
(ticker, website/logo host, alias), never on the LLM-generated name string
alone. Seeded with the three real-world regressions from the 2026-07-13 QA
report (R5)."""
from __future__ import annotations

import pytest

from server import storage


@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "COMPANIES_FILE", tmp_path / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", tmp_path / "threads")
    storage._companies_cache_key = None
    storage._companies_cache_list = []
    storage._companies_cache_index = {}
    storage._reports_cache = {}
    (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _ids():
    return sorted(c["id"] for c in storage.list_companies())


# ---- normalization ----

def test_normalize_strips_trailing_parenthetical_before_suffix():
    # The $-anchored suffix regex used to be defeated by '(AMI Labs)'.
    assert (
        storage._normalize_company_name("Advanced Machine Intelligence Labs, Inc.")
        == "advanced machine intelligence labs"
    )
    assert (
        storage._normalize_company_name(
            "Advanced Machine Intelligence Labs (AMI Labs)"
        )
        == "advanced machine intelligence labs"
    )


def test_normalize_host():
    assert storage._normalize_host("https://www.ami.xyz/about?x=1") == "ami.xyz"
    assert storage._normalize_host("ami.xyz") == "ami.xyz"
    assert storage._normalize_host("WWW.AMI.XYZ") == "ami.xyz"
    assert storage._normalize_host(None) == ""


# ---- the AMI trio collapses to one record ----

AMI_VARIANTS = [
    "Advanced Machine Intelligence Labs (AMI Labs)",
    "Advanced Machine Intelligence, Inc. (AMI Labs)",
    "Advanced Machine Intelligence Labs, Inc.",
]


def test_ami_variants_upsert_to_one_record(tmp_data):
    for name in AMI_VARIANTS:
        storage.upsert_company_from_match(
            {"name": name, "ticker": None, "website": "https://ami.xyz"}
        )
    companies = storage.list_companies()
    assert len(companies) == 1, [c["name"] for c in companies]


def test_alias_match_without_website(tmp_data):
    # Even with no host on the later variant, the alias recorded from the
    # parenthetical keeps matching.
    storage.upsert_company_from_match(
        {"name": "Advanced Machine Intelligence Labs (AMI Labs)", "ticker": None}
    )
    first = storage.list_companies()[0]
    assert "AMI Labs" in (first.get("aliases") or [])
    storage.upsert_company_from_match({"name": "AMI Labs", "ticker": None})
    assert len(storage.list_companies()) == 1


# ---- the goog guard ----

def _seed_goog():
    storage.upsert_company_from_match(
        {
            "name": "Alphabet Inc.",
            "ticker": "GOOG",
            "website": "https://abc.xyz",
            "industry": "Internet & Cloud",
            "hq": "Mountain View, CA",
        }
    )


def test_tickerless_candidate_never_merges_into_tickered_record(tmp_data):
    _seed_goog()
    storage.upsert_company_from_match(
        {
            "name": "Alphabet Inc.",
            "ticker": None,
            "website": "https://alphabetsigns.com",
            "industry": "Signage & Visual Communications",
            "hq": "Dallas, TX",
        }
    )
    companies = storage.list_companies()
    assert len(companies) == 2
    goog = storage.get_company("goog")
    assert goog["industry"] == "Internet & Cloud"
    assert goog["hq"] == "Mountain View, CA"
    assert storage._normalize_host(goog["website"]) == "abc.xyz"


def test_tickered_candidate_still_enriches_goog(tmp_data):
    _seed_goog()
    out = storage.upsert_company_from_match(
        {
            "name": "Alphabet",
            "ticker": "GOOG",
            "website": "https://abc.xyz",
            "employee_band": "100k+",
        }
    )
    assert out["id"] == "goog"
    assert len(storage.list_companies()) == 1
    assert storage.get_company("goog")["employee_band"] == "100k+"


def test_host_disagreement_blocks_name_merge_between_privates(tmp_data):
    storage.upsert_company_from_match(
        {"name": "Acme Robotics", "ticker": None, "website": "acme-robotics.com"}
    )
    storage.upsert_company_from_match(
        {"name": "Acme Robotics", "ticker": None, "website": "acmerobotics.io"}
    )
    assert len(storage.list_companies()) == 2


def test_host_match_beats_name_variation(tmp_data):
    storage.upsert_company_from_match(
        {"name": "Nexus AI", "ticker": None, "website": "https://nexus.ai"}
    )
    out = storage.upsert_company_from_match(
        {"name": "Nexus Artificial Intelligence, Inc.", "ticker": None,
         "logo_domain": "nexus.ai"}
    )
    assert len(storage.list_companies()) == 1
    # The merged-in name variant is remembered as an alias.
    aliases = storage.get_company(out["id"]).get("aliases") or []
    assert any("Nexus Artificial Intelligence" in a for a in aliases)


def test_plain_name_match_between_privates_still_works(tmp_data):
    storage.upsert_company_from_match({"name": "Anduril Industries, Inc.", "ticker": None})
    storage.upsert_company_from_match({"name": "Anduril Industries", "ticker": None})
    assert len(storage.list_companies()) == 1


# ---- resolve_company_match (read-only) ----

def test_resolve_company_match_is_read_only(tmp_data):
    _seed_goog()
    assert storage.resolve_company_match({"name": "x", "ticker": "GOOG"}) == "goog"
    assert (
        storage.resolve_company_match(
            {"name": "Alphabet Inc.", "ticker": None, "website": "alphabetsigns.com"}
        )
        is None
    )
    assert len(storage.list_companies()) == 1


# ---- refresh must never mint a sibling (R5c) ----

def test_deep_search_only_company_id_discards_foreign_matches(
    tmp_data, monkeypatch
):
    from server import cache, companies_ai

    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_data / "cache")
    target = storage.upsert_company_from_match(
        {"name": "Nexus AI", "ticker": None, "website": "https://nexus.ai"}
    )
    raw = [
        # A different company the model returned alongside the target.
        {"name": "Nexus Signage LLC", "ticker": None, "website": "nexussigns.com"},
        # The target, under a new AI-generated name variant.
        {
            "name": "Nexus Artificial Intelligence, Inc.",
            "ticker": None,
            "website": "https://nexus.ai",
            "hq": "Palo Alto, CA",
        },
    ]
    monkeypatch.setattr(companies_ai.claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(
        companies_ai.claude_runner,
        "run_company_search",
        lambda **kwargs: (raw, None),
    )

    result = companies_ai.deep_search(
        "nexus.ai", force_refresh=True, only_company_id=target["id"]
    )
    assert result["source"] == "claude_code"
    # Only the target was persisted — no sibling minted for the foreign match.
    assert len(storage.list_companies()) == 1
    assert storage.get_company(target["id"])["hq"] == "Palo Alto, CA"


def test_deep_search_only_company_id_persists_nothing_on_full_mismatch(
    tmp_data, monkeypatch
):
    from server import cache, companies_ai

    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_data / "cache")
    target = storage.upsert_company_from_match(
        {"name": "Nexus AI", "ticker": None, "website": "https://nexus.ai"}
    )
    before = storage.get_company(target["id"])
    raw = [{"name": "Totally Different Co", "ticker": None, "website": "other.com"}]
    monkeypatch.setattr(companies_ai.claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(
        companies_ai.claude_runner,
        "run_company_search",
        lambda **kwargs: (raw, None),
    )

    result = companies_ai.deep_search(
        "nexus.ai", force_refresh=True, only_company_id=target["id"]
    )
    assert result["matches"] == []
    assert len(storage.list_companies()) == 1
    assert storage.get_company(target["id"]) == before


# ---- legal_name / disambiguator (Phase 4.5) ----

def test_slug_derives_from_legal_name_and_matches_on_it(tmp_data):
    first = storage.upsert_company_from_match(
        {
            "name": "Alphabet Signs",
            "legal_name": "Alphabet Signs, Inc.",
            "disambiguator": "Dallas, TX signage manufacturer",
            "ticker": None,
            "website": "alphabetsigns.com",
        }
    )
    assert first["id"] == "alphabet-signs-inc"
    assert first["disambiguator"] == "Dallas, TX signage manufacturer"
    # A later variant matching only the legal name reconciles to the record.
    out = storage.upsert_company_from_match(
        {"name": "Alphabet Signs, Inc.", "ticker": None}
    )
    assert out["id"] == first["id"]
    assert len(storage.list_companies()) == 1


def test_company_search_prompt_is_identity_first():
    from server import companies_ai

    prompt = companies_ai.SYSTEM_PROMPT
    assert "identity-first" in prompt.lower() or "Work identity-first" in prompt
    assert "HIGH FILL" not in prompt
    assert "full investment analysis" in prompt.lower() or "not a full investment analysis" in prompt
    assert "identification" in prompt.lower()


# ---- a different legal entity on the same website gets its own record (G3) ----
# Every search result is upserted. One 'openai' search turned the OpenAI Group
# PBC record into 'OpenAI Foundation' (nonprofit) through the shared
# openai.com host; one 'cienet technologies' search turned the Beijing CIeNET
# record into Cienet International, LLC of Oak Brook — and three memos ran on
# that record.

OPENAI_PBC = {
    "name": "OpenAI",
    "legal_name": "OpenAI Group PBC",
    "ticker": None,
    "website": "https://openai.com",
    "status": "private",
    "hq": "San Francisco, CA",
    "parent_company": "OpenAI Foundation",
}
CIENET_BEIJING = {
    "name": "CIeNET Technologies",
    "legal_name": "CIeNET Technologies (Beijing) Co., Ltd.",
    "ticker": None,
    "website": "https://www.cienet.com",
    "status": "private",
    "hq": "Beijing, China",
}


@pytest.mark.parametrize("returned_name", ["OpenAI Foundation", "OpenAI"])
def test_openai_foundation_does_not_overwrite_the_pbc_record(tmp_data, returned_name):
    pbc = storage.upsert_company_from_match(dict(OPENAI_PBC))
    foundation = storage.upsert_company_from_match(
        {
            "name": returned_name,
            "legal_name": "OpenAI Foundation",
            "ticker": None,
            "website": "https://openai.com",
            "status": "nonprofit",
            "hq": "San Francisco, CA",
            "parent_company": None,
        }
    )
    assert foundation["id"] == "openai-foundation" != pbc["id"]
    assert _ids() == sorted([pbc["id"], "openai-foundation"])
    kept = storage.get_company(pbc["id"])
    assert kept["legal_name"] == "OpenAI Group PBC"
    assert kept["status"] == "private"
    assert storage.get_company("openai-foundation")["status"] == "nonprofit"
    # The same entity found again still lands on its own record.
    again = storage.upsert_company_from_match({"name": "OpenAI", "legal_name": "OpenAI Group, PBC", "website": "openai.com"})
    assert again["id"] == pbc["id"]


def test_cienet_international_does_not_overwrite_cienet_beijing(tmp_data):
    beijing = storage.upsert_company_from_match(dict(CIENET_BEIJING))
    oak_brook = storage.upsert_company_from_match(
        {
            "name": "Cienet International",
            "legal_name": "Cienet International, LLC",
            "ticker": None,
            "website": "https://cienet.com",
            "status": "private",
            "hq": "Oak Brook, IL",
        }
    )
    assert oak_brook["id"] == "cienet-international-llc" != beijing["id"]
    kept = storage.get_company(beijing["id"])
    assert kept["hq"] == "Beijing, China"
    assert kept["legal_name"] == "CIeNET Technologies (Beijing) Co., Ltd."
    assert storage.resolve_company_match({"name": "Cienet International", "legal_name": "Cienet International LLC", "website": "cienet.com"}) == "cienet-international-llc"


@pytest.mark.parametrize(
    "first, second",
    [
        ("Anthropic PBC", "Anthropic, PBC"),
        ("Anthropic PBC", "Anthropic, Public Benefit Corporation"),
        ("Anduril Industries, Inc.", "Anduril Industries Inc"),
    ],
)
def test_legal_name_spelling_variants_do_not_split(tmp_data, first, second):
    storage.upsert_company_from_match({"name": first.split(",")[0].split(" PBC")[0], "legal_name": first, "website": "https://example-legal.com"})
    storage.upsert_company_from_match({"name": second.split(",")[0], "legal_name": second, "website": "https://example-legal.com"})
    assert len(storage.list_companies()) == 1


def test_an_ordinary_search_fills_identity_fields_but_never_overwrites_them(tmp_data):
    record = storage.upsert_company_from_match(
        {"name": "CIeNET Technologies", "legal_name": "CIeNET Technologies (Beijing) Co., Ltd.", "website": "https://www.cienet.com", "hq": "Beijing, China", "status": "private"}
    )
    storage.upsert_company_from_match(
        {
            "name": "CIeNET Technologies",
            "website": "cienet.com",
            "hq": "Oak Brook, IL",
            "status": "subsidiary",
            "exchange": "OTC",
            "parent_company": "CIeNET Holdings",
            "disambiguator": "Beijing embedded-software services firm",
            "employee_band": "1,000-5,000",
        }
    )
    merged = storage.get_company(record["id"])
    assert merged["hq"] == "Beijing, China"  # identity: kept
    assert merged["status"] == "private"
    assert merged["legal_name"] == "CIeNET Technologies (Beijing) Co., Ltd."
    assert merged["exchange"] == "OTC"  # identity, but empty before: filled
    assert merged["parent_company"] == "CIeNET Holdings"
    assert merged["disambiguator"] == "Beijing embedded-software services firm"
    assert merged["employee_band"] == "1,000-5,000"  # enrichment keeps refreshing


def test_the_explicit_refresh_may_still_overwrite_identity(tmp_data):
    record = storage.upsert_company_from_match(dict(CIENET_BEIJING))
    storage.upsert_company_from_match(
        {"name": "CIeNET Technologies", "legal_name": "CIeNET Technologies (Beijing) Co., Ltd.", "website": "cienet.com", "hq": "Beijing Haidian, China", "ticker": "CNT"},
        overwrite_identity=True,
    )
    refreshed = storage.get_company(record["id"])
    assert refreshed["hq"] == "Beijing Haidian, China"
    # A ticker is only ever filled — here the record had none, so it is.
    assert refreshed["ticker"] == "CNT"
    storage.upsert_company_from_match({"name": "CIeNET Technologies", "ticker": "CNT", "website": "cienet.com"}, overwrite_identity=True)
    storage.upsert_company_from_match({"name": "CIeNET Technologies", "ticker": "CNTX", "website": "cienet.com"}, overwrite_identity=True)
    assert storage.get_company(record["id"])["ticker"] == "CNT"


def test_a_listing_still_updates_a_tickerless_record(tmp_data):
    private = storage.upsert_company_from_match(
        {"name": "Figma", "legal_name": "Figma, Inc.", "website": "https://figma.com", "status": "private", "hq": "San Francisco, CA"}
    )
    listed = storage.upsert_company_from_match(
        {"name": "Figma", "legal_name": "Figma, Inc.", "ticker": "FIG", "exchange": "NYSE", "status": "public", "website": "https://figma.com"}
    )
    assert listed["id"] == private["id"]
    record = storage.get_company(private["id"])
    assert (record["ticker"], record["exchange"], record["status"]) == ("FIG", "NYSE", "public")
    assert record["company_type"] == "public"


def test_deep_search_refresh_overwrites_identity_and_search_dedupes(tmp_data, monkeypatch):
    from server import cache, companies_ai

    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_data / "cache")
    target = storage.upsert_company_from_match(dict(CIENET_BEIJING))
    monkeypatch.setattr(companies_ai.claude_runner, "is_available", lambda: True)
    raw = [
        {"name": "CIeNET Technologies", "legal_name": "CIeNET Technologies (Beijing) Co., Ltd.", "website": "https://cienet.com", "hq": "Beijing Haidian, China"},
        # Two variants of one other company: listed once.
        {"name": "Cienet International", "legal_name": "Cienet International, LLC", "website": "https://cienet.com", "hq": "Oak Brook, IL"},
        {"name": "Cienet International LLC", "legal_name": "Cienet International LLC", "website": "https://cienet.com", "employee_band": "11-50"},
    ]
    monkeypatch.setattr(companies_ai.claude_runner, "run_company_search", lambda **kwargs: (raw, None))

    result = companies_ai.deep_search("cienet", force_refresh=True)
    ids = [row["id"] for row in result["matches"]]
    assert ids == [target["id"], "cienet-international-llc"]
    assert result["matches"][1]["employee_band"] == "11-50"  # the latest merge wins
    # An ordinary search did not move the Beijing record.
    assert storage.get_company(target["id"])["hq"] == "Beijing, China"

    refreshed = companies_ai.deep_search("cienet", force_refresh=True, only_company_id=target["id"])
    assert [row["id"] for row in refreshed["matches"]] == [target["id"]]
    assert storage.get_company(target["id"])["hq"] == "Beijing Haidian, China"
    assert storage.get_company("cienet-international-llc")["hq"] == "Oak Brook, IL"
