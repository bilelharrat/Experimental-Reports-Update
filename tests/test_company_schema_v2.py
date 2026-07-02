from server.api import CompanyOut, _company_view


def test_company_view_preserves_prd_v2_fields_and_typed_competitors():
    raw = {
        "id": "zainar-inc",
        "name": "ZaiNar, Inc.",
        "status": "private",
        "positioning": {"category": "network-based positioning platform"},
        "metrics": [{"label": "Valuation", "value": "$1.0B+"}],
        "team_profiles": [{"name": "Daniel Jacker", "role": "Co-founder"}],
        "competitors": [
            {"id": "nextnav", "name": "NextNav", "status": "Public"},
        ],
        "board_investors": [{"name": "Future Ventures", "role": "Lead"}],
        "cap_table_lineage": [{"name": "Founders", "ownership": "65.0%"}],
        "company_news": [{"title": "Launch", "category": "fundraising"}],
        "industry_view": {"metrics": [{"label": "Sector TAM", "value": "~$45B"}]},
        "expert_opinions": [{"speaker": "BSH", "stance": "Cautious"}],
        "disclosures": [{"label": "Position disclosure"}],
    }

    payload = CompanyOut(**_company_view(raw))

    assert payload.positioning["category"] == "network-based positioning platform"
    assert payload.metrics[0]["value"] == "$1.0B+"
    assert payload.team_profiles[0]["name"] == "Daniel Jacker"
    assert payload.competitors[0]["name"] == "NextNav"
    assert payload.board_investors[0]["name"] == "Future Ventures"
    assert payload.cap_table_lineage[0]["ownership"] == "65.0%"
    assert payload.company_news[0]["category"] == "fundraising"
    assert payload.industry_view["metrics"][0]["label"] == "Sector TAM"
    assert payload.expert_opinions[0]["stance"] == "Cautious"
    assert payload.disclosures[0]["label"] == "Position disclosure"


def test_company_view_keeps_legacy_string_competitors_valid():
    payload = CompanyOut(
        **_company_view(
            {
                "id": "legacy",
                "name": "Legacy Co",
                "status": "private",
                "competitors": ["NextNav", "Skyhook"],
            },
        ),
    )

    assert payload.competitors == ["NextNav", "Skyhook"]
