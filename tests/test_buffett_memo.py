from __future__ import annotations

import json
from pathlib import Path

from docx import Document

from server import api as api_module
from server import buffett_memo_renderer, claude_runner, memo_prep


def _pad(text: str, *, minimum: int = 850) -> str:
    filler = (
        " Owner's earnings, as I figure them, are the cash that can be taken "
        "out of the business without impairing its competitive position. I "
        "would rather be approximately right than precisely wrong, and I will "
        "not pay today for a story that has to come true next year. "
    )
    while len(text) < minimum:
        text += filler
    return text


def _english_memo(*, decision: str = "Pass") -> str:
    return _pad(
        f"""# Investment Memorandum — Example Co

Omaha, August 2026

## I. Investment Decision

{decision}. I would not buy the whole company at the last disclosed price.
The economics are intelligible, but the price offers no margin of safety.

## II. The Business

Example Co sells industrial software to factories. Customers pay annually.
The product is useful, not magical.

## III. Circle of Competence

I understand how a factory pays for software that reduces downtime. This sits
inside my circle.

## IV. Economic Characteristics

Returns on tangible capital look decent where disclosed, but incremental
reinvestment needs are not proven. I will not capitalize hoped-for scale.

## V. Durable Competitive Advantage

Switching costs exist once the software is on the floor, yet a well-capitalized
rival can still buy the next plant. The moat is narrow, not a toll bridge.

## VI. Management and Capital Allocation

Management appears able. I have no long record of owner-oriented capital
allocation, so I assume average until proven otherwise.

## VII. Financial Position

The balance sheet is not stretched. Leverage is not the issue; price is.

## VIII. Intrinsic Value and Margin of Safety

I would pay a price that capitalizes current owner's earnings at a conservative
rate. Today's quote, if the last round is a guide, is closer to a wonderful
price for a fair business than a fair price for a wonderful business.

## IX. What Can Go Permanently Wrong

Paying too much. A competitor giving the product away. Key-person risk if the
founders leave. Dilution to fund growth that does not earn its keep.

## X. Conclusion

{decision}. I would be happy to own the whole business only at a lower price.
If the market closed for ten years, I would not want this as a large holding
at the current valuation.
"""
    )


def _chinese_memo(*, decision_zh: str = "放弃") -> str:
    return _pad(
        f"""# 投资备忘录 — Example Co

奥马哈，2026年8月

## 一、投资决策

{decision_zh}。按最近一轮披露的价格，我不会买下整家公司。生意能看懂，但没有安全边际。

## 二、这家企业

Example Co 向工厂出售工业软件，客户按年付费。产品有用，但并不神奇。

## 三、能力圈

我理解工厂为何为减少停机的软件付钱。这在我的能力圈内。

## 四、经济特征

有披露的有形资本回报看起来尚可，但再投资需求未经证明。我不会把明年的故事资本化。

## 五、持久竞争优势

上线后有一定转换成本，但有资本的对手仍可拿下下一家工厂。护城河很窄。

## 六、管理层与资本配置

管理层看起来能干。我没有长期的所有者导向资本配置记录，因此先按平均水平假设。

## 七、财务状况

资产负债表并不紧。问题不在杠杆，而在价格。

## 八、内在价值与安全边际

我会按保守利率资本化当前股东盈余（owner's earnings）。若上一轮定价可参考，今天更像是给平庸生意付了美妙价格。

## 九、可能造成永久损失的因素

买贵了。对手免费送产品。创始人离开。为增长而稀释却赚不回资本成本。

## 十、结论

{decision_zh}。只有更低的价格我才愿意拥有整家公司。若市场关闭十年，我不会把当前估值下的这家公司当作重仓。
"""
    )


def test_report_types_include_buffett_memo():
    assert memo_prep.BUFFETT_REPORT_TYPE in api_module.REPORT_TYPES
    assert memo_prep.REPORT_TYPE in api_module.REPORT_TYPES
    assert memo_prep.is_memo_report_type(memo_prep.BUFFETT_REPORT_TYPE)
    assert memo_prep.is_buffett_kind(memo_prep.BUFFETT_KIND)
    assert not memo_prep.is_buffett_kind(memo_prep.LATESTAGE_KIND)


def test_buffett_filename_and_run_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(memo_prep, "MEMOS_ROOT", tmp_path / "memos")
    name = memo_prep._memo_filename("Acme", "2026-08-20__120000", "en", buffett=True)
    assert name == "Acme - Buffett Investment Memo - 2026-08-20__120000.docx"
    zh = memo_prep._memo_filename("Acme", "2026-08-20__120000", "zh", buffett=True)
    assert "巴菲特投资备忘录" in zh
    run_dir = memo_prep._make_run_dir(
        "acme", "2026-08-20__120000", run_suffix="buffett-memo-run"
    )
    assert run_dir.name.endswith("__buffett-memo-run")
    assert (run_dir / "memo").is_dir()


def test_buffett_prompt_is_first_person_not_bsh_lp(tmp_path):
    companies = tmp_path / "companies.yaml"
    companies.write_text("companies: []\n", encoding="utf-8")
    prompt = claude_runner._build_buffett_investment_memo_prompt(
        run_dir=tmp_path,
        company_name="Example Co",
        company_slug="example-co",
        run_id="2026-08-20__120000",
        companies_yaml_path=companies,
        memo_paths={
            "en": str(tmp_path / "memo" / "en.docx"),
            "zh": str(tmp_path / "memo" / "zh.docx"),
        },
        scope_check={
            "outcome": "warn",
            "classification": "early-stage",
            "reason": "Latest funding round 'series a' is early-stage.",
        },
        warnings=["Latest funding round 'series a' is early-stage."],
    )
    assert "Warren Buffett" in prompt
    assert "Buy / Pass / Too Hard" in prompt
    assert "Do not adopt BSH LP sell-side voice" in prompt
    assert "The author is Warren Buffett" in prompt
    assert "owner's earnings" in prompt.lower()
    assert "bsh-buffett-investment-memo-v1" in prompt
    assert "Too Hard" in prompt


def test_buffett_package_renders_docx(tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "memo").mkdir()
    package = {
        "schema_version": 1,
        "kind": "buffett_investment_memo",
        "company_name": "Example Co",
        "decision": "Pass",
        "buy_price": "$8 a share",
        "markdown_en": _english_memo(),
        "markdown_zh": _chinese_memo(),
    }
    (run_dir / "logs" / "memo_package.json").write_text(
        json.dumps(package, ensure_ascii=False),
        encoding="utf-8",
    )
    en_docx = run_dir / "memo" / "en.docx"
    zh_docx = run_dir / "memo" / "zh.docx"
    loaded = buffett_memo_renderer.load_package(run_dir)
    rendered = buffett_memo_renderer.render_package(
        loaded,
        run_dir=run_dir,
        memo_paths={"en": en_docx, "zh": zh_docx},
    )
    assert rendered["ok"] is True
    assert rendered["decision"] == "Pass"
    assert en_docx.exists()
    assert zh_docx.exists()
    english = Document(str(en_docx))
    text = "\n".join(p.text for p in english.paragraphs)
    assert "Investment Decision" in text
    assert "Pass" in text
    assert (run_dir / "memo" / "buffett_memo.en.md").exists()


def test_buffett_package_rejects_bsh_structure():
    package = {
        "schema_version": 1,
        "kind": "buffett_investment_memo",
        "company_name": "Example Co",
        "decision": "Buy",
        "markdown_en": "# Not a Buffett memo\n\nWe recommend participating.\n",
        "markdown_zh": "# 不是巴菲特备忘录\n\n我们建议参与。\n",
    }
    try:
        buffett_memo_renderer.validate_package(package)
    except buffett_memo_renderer.BuffettMemoPackageError as exc:
        message = str(exc)
        assert "too short" in message or "missing heading" in message
    else:
        raise AssertionError("expected BuffettMemoPackageError")


def test_buffett_bootstrap_dispatches_to_buffett_worker(tmp_path, monkeypatch):
    from server import buffett_memo_analysis, storage

    started: list[tuple[str, str]] = []
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "COMPANIES_FILE", tmp_path / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(memo_prep, "DATA_DIR", tmp_path)
    monkeypatch.setattr(memo_prep, "MEMOS_ROOT", tmp_path / "memos")
    monkeypatch.setattr(
        memo_prep,
        "SETTINGS_FILE",
        tmp_path / "settings" / "serena_background.md",
    )
    monkeypatch.setattr(memo_prep, "COMPANIES_FILE", tmp_path / "companies.yaml")
    memo_prep.SETTINGS_FILE.parent.mkdir(parents=True)
    memo_prep.SETTINGS_FILE.write_text("background\n", encoding="utf-8")
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [
            {
                "id": "example-co",
                "name": "Example Co",
                "status": "private",
                "description": "A software company.",
            }
        ],
    )
    monkeypatch.setattr(
        buffett_memo_analysis,
        "start_analysis",
        lambda report_id: started.append(("buffett", report_id)),
    )
    from server import memo_analysis

    monkeypatch.setattr(
        memo_analysis,
        "start_analysis",
        lambda report_id: started.append(("latestage", report_id)),
    )

    result = memo_prep.bootstrap_memo_run(
        "example-co",
        report_type=memo_prep.BUFFETT_REPORT_TYPE,
    )
    assert result["failed"] is False
    report = storage.get_report(result["report_id"])
    assert report["kind"] == memo_prep.BUFFETT_KIND
    assert report["report_type"] == memo_prep.BUFFETT_REPORT_TYPE
    assert report["skill"] == memo_prep.BUFFETT_SKILL_NAME
    assert started == [("buffett", report["id"])]
    assert "buffett-memo-run" in str(result["run_dir"])
    manifest = Path(result["manifest_path"]).read_text(encoding="utf-8")
    assert "bsh-buffett-investment-memo-v1" in manifest
    assert "serena_background.md" not in manifest
