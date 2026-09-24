"""Realistic structure-v2 memo packages for renderer regression tests.

Two packages the pipeline would hand the renderer now that the v2 memo is
the default (``BSH_MEMO_STRUCTURE_V2``): the full twelve-section
``late_v2`` memo and the seven-section ``late_compact`` one, both in
English and Chinese. They carry what live v2 runs carry and the five v1
packages on disk do not: the fixed numbered subsections, the key-metrics,
deal-terms, scenario and scorecard tables, inline ``[S#]`` / ``[C#]``
citations, pinned calculation notes, 8-row risk cards, chart blocks with
their readings, and a sources list with URLs, tiers and honest dates.

The company is fictional (Veltrix Systems). Chinese figures keep the
"$24M" form exactly as the model writes them (owner decision 2026-09-22).
Plain module, not a test file: ``from memo_v2_fixture import ...``.
"""
from __future__ import annotations

import copy

from server import memo_structure

V2 = memo_structure.load_structure("late", 2)
COMPACT = memo_structure.load_structure("late_compact", 1)


def L(en: str, zh: str) -> dict:
    return {"en": en, "zh": zh}


def para(en: str, zh: str, **extra) -> dict:
    return {"type": "paragraph", "text": L(en, zh), **extra}


def heading(en: str, zh: str, level: int = 2) -> dict:
    return {"type": "heading", "level": level, "text": L(en, zh)}


def table(
    title: tuple[str, str] | None,
    headers: list,
    rows: list,
    *,
    component: str | None = None,
    layout: str | None = None,
) -> dict:
    block: dict = {"type": "table", "headers": headers, "rows": rows}
    if title:
        block["title"] = L(*title)
    if component:
        block["component"] = component
    if layout:
        block["layout"] = layout
    return block


def chart(
    chart_type: str,
    title: tuple[str, str],
    series: list[dict],
    *,
    unit: tuple[str, str] | str,
    reading: tuple[str, str],
    caption: tuple[str, str],
    source_ids: list[str],
    **extra,
) -> dict:
    return {
        "type": "chart",
        "chart_type": chart_type,
        "title": L(*title),
        "unit": L(*unit) if isinstance(unit, tuple) else unit,
        "reading": L(*reading),
        "caption": L(*caption),
        "series": series,
        "source_ids": source_ids,
        **extra,
    }


def _sub(structure: memo_structure.MemoStructure, section_id: str, number: int) -> dict:
    sub = structure.section(section_id).subsections[number - 1]
    return heading(f"{number}. {sub.en}", f"{number}. {sub.zh}")


# ---- shared pieces -----------------------------------------------------------------

COMPANY = {
    "name": L("Veltrix Systems, Inc.", "维特瑞斯系统（Veltrix）"),
    "descriptor": L(
        "Battery analytics and dispatch software for grid-scale storage",
        "面向电网级储能的电池分析与调度软件",
    ),
    "stage": L("Late-stage / pre-IPO", "后期 / IPO 前"),
    "sector": L("Energy software", "能源软件"),
    "location": L("Austin, Texas", "美国得克萨斯州奥斯汀"),
    "round": L("Series D, $180M at $2.4B post-money", "D 轮，融资 $180M，投后估值 $2.4B"),
    "website": "https://www.veltrix.example",
}

RUN = {
    "run_id": "2026-09-18__101500",
    "as_of": "2026-09-18",
    "evidence_cutoff": "2026-09-12",
    "checks": {
        "fact_check": {
            "verified": 61,
            "found_elsewhere": 14,
            "derived": 9,
            "not_traced": 4,
            "thin_corpus": False,
        },
        "gates": {"quality": "passed", "chinese_parity": "passed", "fact_check": "warnings"},
    },
    "review": {"state": "draft"},
}


def _source(
    sid: str,
    title_en: str,
    title_zh: str,
    source_class: str,
    treatment: tuple[str, str],
    *,
    url: str | None = None,
    **dates,
) -> dict:
    source = {
        "id": sid,
        "title": L(title_en, title_zh),
        "class": source_class,
        "treatment": L(*treatment),
    }
    if url:
        source["url"] = url
    source.update(dates)
    return source


SOURCES = [
    _source("S1", "Veltrix announces $180M Series D", "Veltrix 宣布完成 $180M D 轮融资", "company announcement",
            ("Round size, lead and post-money valuation.", "融资规模、领投方与投后估值。"),
            url="https://www.veltrix.example/news/series-d", published_at="2026-08-04", retrieved_at="2026-09-15"),
    _source("S2", "Form D — Veltrix Systems, Inc.", "Form D 备案——Veltrix Systems, Inc.", "regulatory filing",
            ("Amount sold and investor count; confirms the raise.", "已售金额与投资人数量，确认本轮融资。"),
            url="https://www.sec.gov/Archives/edgar/data/1990001/000199000126000004/xslFormDX01/primary_doc.xml",
            published_at="2026-08-11"),
    _source("S3", "Reuters — Veltrix revenue passes $86M as utilities add storage", "路透社——公用事业扩充储能，Veltrix 收入突破 $86M",
            "business press", ("Fiscal 2025 revenue and growth, company-sourced.", "2025 财年收入与增速（公司口径）。"),
            url="https://www.reuters.com/business/energy/veltrix-revenue-2026-03-12/", published_at="2026-03-12",
            data_period="2025"),
    _source("S4", "Bloomberg — Grid software valuations after the storage boom", "彭博——储能热潮后的电网软件估值",
            "business press", ("Peer revenue multiples and recent marks.", "可比公司收入倍数与近期估值。"),
            url="https://www.bloomberg.com/news/articles/2026-07-21/grid-software-valuations", published_at="2026-07-21"),
    _source("S5", "Veltrix management presentation (data room)", "Veltrix 管理层演示材料（资料室）", "company materials",
            ("Cohort retention, pipeline and the 2026 plan; company claims.", "客户留存、销售管线与 2026 年计划；公司口径。"),
            published_at="2026-08"),
    _source("S6", "Management call with the CFO", "与首席财务官的管理层访谈", "management interview",
            ("Contract structure and pricing; oral, not documented.", "合同结构与定价；口头信息，无书面文件。"),
            published_at="2026-09-02"),
    _source("S7", "IEA — Batteries and Secure Energy Transitions", "国际能源署——电池与能源安全转型", "industry research",
            ("Global storage deployment path to 2030.", "至 2030 年全球储能部署路径。"),
            url="https://www.iea.org/reports/batteries-and-secure-energy-transitions", published_at="2025-04",
            data_period="2024"),
    _source("S8", "Wood Mackenzie — US energy storage monitor, Q2 2026", "伍德麦肯兹——美国储能市场监测（2026 年第二季度）",
            "syndicated market research", ("US installations and the utility-scale share.", "美国装机量与电网级占比。"),
            url="https://www.woodmac.com/industry/power-and-renewables/us-energy-storage-monitor/", published_at="2026-06"),
    _source("S9", "Fluence Energy 10-K (fiscal 2025)", "Fluence Energy 10-K 年报（2025 财年）", "public filing",
            ("Competitor software revenue and margins.", "竞争对手软件收入与利润率。"),
            url="https://www.sec.gov/Archives/edgar/data/1868941/000186894125000012/flnc-20250930.htm",
            published_at="2025-11-26", data_period="2025"),
    _source("S10", "TechCrunch — Veltrix lands its tenth utility", "TechCrunch——Veltrix 签下第十家公用事业客户",
            "third party press", ("Customer count and named utilities.", "客户数量与具名公用事业客户。"),
            url="https://techcrunch.com/2026/05/14/veltrix-tenth-utility/", published_at="2026-05-14"),
    _source("S11", "FERC Order No. 2023 compliance filings", "美国联邦能源管理委员会第 2023 号令合规申报", "regulatory filing",
            ("Interconnection queue reform timeline.", "并网排队改革时间表。"),
            url="https://www.ferc.gov/media/order-no-2023", published_at="2025-02"),
    _source("S12", "PitchBook — Veltrix Systems profile", "PitchBook——Veltrix Systems 公司档案", "data vendor",
            ("Funding history and prior marks.", "融资历史与此前估值。"),
            url="https://pitchbook.com/profiles/company/498231-10", published_at="2026-08-20"),
    _source("S13", "Energy blog — why battery software margins are overstated", "能源博客——电池软件利润率为何被高估",
            "aggregator", ("Low weight; one practitioner's margin estimate.", "低权重；个人从业者的利润率估算。"),
            url="https://storagenotes.example.com/battery-software-margins", published_at="undated"),
    _source("S14", "Tesla Q2 2026 update (Autobidder)", "特斯拉 2026 年第二季度报告（Autobidder）", "public filing",
            ("Competitor bundling of dispatch software with hardware.", "竞争对手将调度软件与硬件捆绑销售。"),
            url="https://www.sec.gov/Archives/edgar/data/1318605/000131860526000089/tsla-q2.htm", published_at="2026-07-23"),
    _source("S15", "Veltrix reference calls (three utilities)", "Veltrix 客户背景调查访谈（三家公用事业公司）", "reference calls",
            ("Renewal intent and switching cost, three of eleven customers.", "续约意向与切换成本，覆盖 11 家客户中的 3 家。"),
            published_at="2026-09-05"),
    _source("S16", "Financial Times — Storage developers squeeze software vendors", "金融时报——储能开发商压缩软件供应商价格",
            "business press", ("Price pressure on per-MWh software fees.", "按兆瓦时计费的软件价格承压。"),
            url="https://www.ft.com/content/storage-software-pricing-2026", published_at="2026-06-30"),
]


CALCULATIONS = [
    {
        "id": "C1",
        "label": L("Entry revenue multiple", "入场收入倍数"),
        "inputs": [
            {"name": "post-money valuation", "value": "$2.4B", "ref": "S1"},
            {"name": "2025 revenue", "value": "$86M", "ref": "S3"},
        ],
        "formula": "$2.4B ÷ $86M = 27.9x",
        "result": "27.9x",
        "meaning": L("The price is about 28 times last year's revenue.", "价格约为上一年收入的 28 倍。"),
    },
    {
        "id": "C2",
        "label": L("Base-case MOIC", "基准情形回报倍数"),
        "inputs": [
            {"name": "2030 revenue", "value": "$420M", "ref": "S5"},
            {"name": "exit multiple", "value": "10x", "ref": "S4"},
            {"name": "dilution to exit", "value": "15%", "ref": "assumption"},
        ],
        "formula": "$420M × 10 = $4.2B; $4.2B × 0.85 ÷ $2.4B = 1.49x",
        "result": "1.5x",
        "meaning": L("About 9% a year over a four-and-a-half-year hold.", "持有约四年半，年化回报约 9%。"),
    },
    {
        "id": "C3",
        "label": L("Bear-case MOIC", "悲观情形回报倍数"),
        "inputs": [
            {"name": "2030 revenue", "value": "$210M", "ref": "S5"},
            {"name": "exit multiple", "value": "6x", "ref": "S4"},
        ],
        "formula": "$210M × 6 = $1.26B; $1.26B × 0.85 ÷ $2.4B = 0.45x",
        "result": "0.45x",
        "meaning": L("A loss of more than half the capital.", "损失超过一半本金。"),
    },
    {
        "id": "C4",
        "label": L("Bull-case MOIC", "乐观情形回报倍数"),
        "inputs": [
            {"name": "2030 revenue", "value": "$640M", "ref": "S5"},
            {"name": "exit multiple", "value": "12x", "ref": "S4"},
        ],
        "formula": "$640M × 12 = $7.68B; $7.68B × 0.85 ÷ $2.4B = 2.72x",
        "result": "2.7x",
        "meaning": L("A strong outcome that needs the plan and a premium multiple.", "需要计划兑现且获得溢价倍数的强劲结果。"),
    },
    {
        "id": "C5",
        "label": L("Net revenue retention", "净收入留存率"),
        "inputs": [
            {"name": "2024 cohort revenue in 2025", "value": "$41.4M", "ref": "S5"},
            {"name": "2024 cohort revenue in 2024", "value": "$30.0M", "ref": "S5"},
        ],
        "formula": "$41.4M ÷ $30.0M = 138%",
        "result": "138%",
        "meaning": L("Existing customers grew their spend by more than a third.", "现有客户的支出增长超过三分之一。"),
    },
    {
        "id": "C6",
        "label": L("Growth factor vs multiple factor", "增长因子与倍数因子"),
        "inputs": [
            {"name": "revenue 2025 to 2030", "value": "$86M to $420M", "ref": "S5"},
            {"name": "multiple entry to exit", "value": "27.9x to 10x", "ref": "C1"},
        ],
        "formula": "$420M ÷ $86M = 4.88; 10 ÷ 27.9 = 0.36; 4.88 × 0.36 × 0.85 = 1.49",
        "result": "4.9x growth × 0.36x multiple",
        "meaning": L("Growth carries the return; the multiple takes most of it back.", "回报来自增长，但倍数收缩抵消了大部分。"),
    },
]


def _risk_card(number: int, title: tuple[str, str], rows: dict[str, tuple[str, str]]) -> list[dict]:
    order = (
        ("Risk Type", "风险类型"),
        ("Verdict", "结论"),
        ("Impact", "影响"),
        ("Why it matters", "为何重要"),
        ("What we watch", "观察指标"),
        ("Mitigation", "缓释因素"),
        ("Likelihood", "可能性"),
        ("Risk Rating", "风险评级"),
    )
    return [
        heading(f"Risk {number}: {title[0]}", f"风险 {number}：{title[1]}", level=3),
        table(
            None,
            [],
            [[L(en_label, zh_label), L(*rows[en_label])] for en_label, zh_label in order],
            component="risk_register",
            layout="key_value",
        ),
    ]


RISK_CARDS = [
    (
        ("The entry price already assumes the 2030 plan is delivered", "入场价格已经假设 2030 年计划全部兑现"),
        {
            "Risk Type": ("Valuation & exit", "估值与退出"),
            "Verdict": ("The price leaves no room for a miss [C1].", "价格没有为计划落空留出空间 [C1]。"),
            "Impact": ("Base case returns 1.5x; a one-year slip takes it near 1.1x [C2].", "基准情形回报 1.5 倍；推迟一年则接近 1.1 倍 [C2]。"),
            "Why it matters": (
                "At 27.9x revenue the exit multiple must fall to 10x, so revenue has to grow 4.9x just to return 1.5x on the capital [C6].",
                "以 27.9 倍收入入场，退出倍数需降至 10 倍，收入必须增长 4.9 倍才能实现 1.5 倍回报 [C6]。",
            ),
            "What we watch": ("Quarterly revenue against the $118M 2026 plan [S5].", "季度收入与 2026 年 $118M 计划的对比 [S5]。"),
            "Mitigation": ("A 1x liquidation preference protects the downside below $1.2B of exit value.", "1 倍清算优先权在退出估值低于 $1.2B 时提供保护。"),
            "Likelihood": ("High: the plan needs 37% growth a year for five years.", "高：计划要求五年内每年增长 37%。"),
            "Risk Rating": ("9/10: it decides the return.", "9/10：它决定了回报。"),
        },
    ),
    (
        ("Hardware vendors bundle dispatch software for free", "硬件厂商免费捆绑调度软件"),
        {
            "Risk Type": ("Competition", "竞争"),
            "Verdict": ("Bundling caps price, not adoption [S14].", "捆绑限制的是价格，而非采用率 [S14]。"),
            "Impact": ("A 20% fee cut removes about $17M of 2026 revenue.", "费用下调 20% 将减少约 $17M 的 2026 年收入。"),
            "Why it matters": (
                "Tesla and Fluence ship dispatch with the battery, which pushes the per-MWh fee down and compresses gross margin [S9].",
                "特斯拉和 Fluence 随电池附带调度软件，压低按兆瓦时计费的价格并压缩毛利率 [S9]。",
            ),
            "What we watch": ("Win rate against bundled bids in utility tenders.", "公用事业招标中对捆绑报价的中标率。"),
            "Mitigation": ("Multi-vendor fleets need a neutral layer; eight of eleven customers run two or more brands [S15].", "多品牌储能需要中立的软件层；11 家客户中有 8 家使用两个以上品牌 [S15]。"),
            "Likelihood": ("Medium: bundling is spreading but utilities resist lock-in.", "中：捆绑在扩散，但公用事业抵触锁定。"),
            "Risk Rating": ("8/10: it sets the margin ceiling.", "8/10：它决定利润率上限。"),
        },
    ),
    (
        ("Three utilities make up half of revenue", "三家公用事业贡献一半收入"),
        {
            "Risk Type": ("Concentration", "集中度"),
            "Verdict": ("One lost renewal would reset the growth rate.", "失去一个续约就会改变增长率。"),
            "Impact": ("The largest customer is 22% of revenue, about $19M [S5].", "最大客户占收入 22%，约 $19M [S5]。"),
            "Why it matters": (
                "Utility contracts renew every three years, so one non-renewal would cut revenue growth from 37% to about 15%.",
                "公用事业合同每三年续约一次，一次不续约将使收入增速从 37% 降至约 15%。",
            ),
            "What we watch": ("The top-three share of revenue each quarter.", "每季度前三大客户收入占比。"),
            "Mitigation": ("Renewals are staggered across 2027, 2028 and 2029.", "续约时间分散在 2027、2028 和 2029 年。"),
            "Likelihood": ("Medium: two of three references plan to renew [S15].", "中：三位受访客户中有两位计划续约 [S15]。"),
            "Risk Rating": ("7/10: large but staggered.", "7/10：影响大但时间分散。"),
        },
    ),
    (
        ("Interconnection delays push out new storage sites", "并网延误推迟新储能项目"),
        {
            "Risk Type": ("Market", "市场"),
            "Verdict": ("Queue reform helps after 2027, not before [S11].", "排队改革在 2027 年后才见效 [S11]。"),
            "Impact": ("A two-quarter delay moves $9M of new-site revenue into 2027.", "推迟两个季度会使 $9M 新项目收入推迟到 2027 年。"),
            "Why it matters": (
                "New sites drive a third of bookings, so a slower queue delays revenue and lengthens the cash burn.",
                "新项目贡献三分之一的订单，排队放缓会推迟收入并延长现金消耗。",
            ),
            "What we watch": ("Interconnection approvals in ERCOT and CAISO each quarter [S8].", "ERCOT 与 CAISO 每季度的并网批准数量 [S8]。"),
            "Mitigation": ("Retrofits of existing fleets are two thirds of the pipeline.", "现有储能的改造项目占销售管线的三分之二。"),
            "Likelihood": ("Medium: delays are common but already in the plan.", "中：延误常见，但已计入计划。"),
            "Risk Rating": ("6/10: timing, not direction.", "6/10：影响时间而非方向。"),
        },
    ),
    (
        ("Per-MWh pricing falls as developers consolidate", "开发商整合导致按兆瓦时价格下降"),
        {
            "Risk Type": ("Commercialization", "商业化"),
            "Verdict": ("Price pressure is real and early [S16].", "价格压力真实存在且已出现 [S16]。"),
            "Impact": ("Every 10% price cut lowers gross margin by about 3 points.", "价格每下降 10%，毛利率下降约 3 个百分点。"),
            "Why it matters": (
                "Large developers now negotiate portfolio pricing, which lowers revenue per MWh and the margin on each new site.",
                "大型开发商开始按资产组合议价，降低了每兆瓦时收入和每个新项目的利润率。",
            ),
            "What we watch": ("Average revenue per MWh under management [S5].", "每兆瓦时管理容量的平均收入 [S5]。"),
            "Mitigation": ("Optimization fees tie price to the revenue Veltrix earns for the owner.", "优化费用将价格与 Veltrix 为业主创造的收益挂钩。"),
            "Likelihood": ("Medium: two large contracts renegotiated in 2026.", "中：2026 年已有两份大合同重新议价。"),
            "Risk Rating": ("5/10: margin, not survival.", "5/10：影响利润率而非生存。"),
        },
    ),
    (
        ("The founder still runs product and sales", "创始人仍同时负责产品与销售"),
        {
            "Risk Type": ("Team, governance & regulation", "团队、治理与监管"),
            "Verdict": ("A thin bench for a company planning a listing.", "对计划上市的公司而言，管理梯队偏薄。"),
            "Impact": ("An IPO slips a year without a public-company CFO and sales head.", "若没有具备上市公司经验的 CFO 和销售负责人，IPO 将推迟一年。"),
            "Why it matters": (
                "A delayed listing extends the hold and lowers the IRR on the same exit value.",
                "上市推迟会延长持有期，在退出估值不变时降低内部收益率。",
            ),
            "What we watch": ("Senior hires announced before the 2027 audit.", "2027 年审计前公布的高管招聘。"),
            "Mitigation": ("The board added an independent audit chair in 2026 [S12].", "董事会于 2026 年新增一名独立审计委员会主席 [S12]。"),
            "Likelihood": ("Low: the search is under way.", "低：招聘已在进行。"),
            "Risk Rating": ("4/10: fixable with hires.", "4/10：可通过招聘解决。"),
        },
    ),
]


# ---- late v2 (twelve sections) ---------------------------------------------------


def _scorecard_sentence(score: int, weight: int) -> dict:
    return para(
        f"This dimension scores {score} of {weight}.",
        f"该维度得分 {score}/{weight}。",
    )


def late_v2_package() -> dict:
    s = lambda sid, n: _sub(V2, sid, n)  # noqa: E731
    sections = [
        {
            "id": "executive_summary",
            "blocks": [
                s("executive_summary", 1),
                para(
                    "Veltrix sells software that decides when grid batteries charge and discharge, to US utilities and storage owners. It manages 9.4 GWh across eleven utilities and reached $86M of revenue in 2025 [S3], placing it at the pre-IPO rung of the late-stage ladder.",
                    "Veltrix 为美国公用事业和储能业主提供决定电网电池何时充放电的软件，目前管理 11 家公用事业客户的 9.4 GWh 储能，2025 年收入达到 $86M [S3]，处于后期阶段中的 IPO 前阶段。",
                ),
                s("executive_summary", 2),
                para(
                    "The Series D raises $180M at a $2.4B post-money valuation [S1], confirmed by the Form D [S2]. At 27.9x last year's revenue [C1], the price already includes most of the 2030 plan.",
                    "D 轮融资 $180M，投后估值 $2.4B [S1]，已由 Form D 备案确认 [S2]。按上一年收入的 27.9 倍计算 [C1]，价格已经包含了 2030 年计划的大部分。",
                ),
                s("executive_summary", 3),
                para(
                    "Veltrix's case rests on market size and growth (13/15) and revenue growth and quality (12/15); it is thinnest on valuation (3/10) and exit certainty (2/5).",
                    "Veltrix 的投资逻辑主要依靠市场空间与增速（13/15）和收入增长与质量（12/15）；最薄弱的是估值（3/10）和退出确定性（2/5）。",
                ),
                {
                    "type": "bullets",
                    "component": "investment_highlights",
                    "items": [
                        L(
                            "Storage is the fastest-growing asset on the US grid. The IEA expects global storage capacity to grow sixfold by 2030 [S7], and US utility-scale installations doubled in 2025 [S8].",
                            "储能是美国电网增长最快的资产。国际能源署预计到 2030 年全球储能容量将增长六倍 [S7]，2025 年美国电网级装机量翻了一番 [S8]。",
                        ),
                        L(
                            "Existing customers expand quickly. Net revenue retention was 138% for the 2024 cohort [C5], and no utility has left since 2021 [S5].",
                            "现有客户扩张迅速。2024 年客户群的净收入留存率为 138% [C5]，自 2021 年以来没有公用事业客户流失 [S5]。",
                        ),
                        L(
                            "The software is brand-neutral in a multi-vendor market. Eight of eleven customers run batteries from two or more makers [S15].",
                            "在多品牌市场中，软件保持品牌中立。11 家客户中有 8 家使用两个以上厂商的电池 [S15]。",
                        ),
                    ],
                },
                s("executive_summary", 4),
                {
                    "type": "bullets",
                    "component": "key_risks",
                    "items": [
                        L(
                            "Valuation & exit — The entry price already assumes the 2030 plan is delivered. Impact: the base case returns 1.5x [C2]. (9/10, High likelihood)",
                            "估值与退出——入场价格已经假设 2030 年计划全部兑现。影响：基准情形回报 1.5 倍 [C2]。（9/10，可能性高）",
                        ),
                        L(
                            "Competition — Hardware vendors bundle dispatch software for free. Impact: a 20% fee cut removes about $17M of 2026 revenue. (8/10, Medium likelihood)",
                            "竞争——硬件厂商免费捆绑调度软件。影响：费用下调 20% 将减少约 $17M 的 2026 年收入。（8/10，可能性中等）",
                        ),
                        L(
                            "Concentration — Three utilities make up half of revenue. Impact: the largest customer is 22% of revenue [S5]. (7/10, Medium likelihood)",
                            "集中度——三家公用事业贡献一半收入。影响：最大客户占收入 22% [S5]。（7/10，可能性中等）",
                        ),
                    ],
                },
                s("executive_summary", 5),
                {
                    "type": "callout",
                    "title": L("Recommendation", "投资建议"),
                    "body": L(
                        "Recommendation: pass at $2.4B; BSH commits only at or below $1.6B post-money, where the base case returns 2.2x. Watch — 68/100.",
                        "投资建议：在 $2.4B 估值下放弃；仅当投后估值不高于 $1.6B、基准情形回报达到 2.2 倍时，BSH 才出资。观察名单——68/100。",
                    ),
                },
            ],
        },
        {
            "id": "company_overview",
            "blocks": [
                s("company_overview", 1),
                para(
                    "Veltrix was founded in 2019 and employs about 240 people [S12]. Revenue grew 72% in 2025 [S3]; gross margin was 71% [S5].",
                    "Veltrix 成立于 2019 年，员工约 240 人 [S12]。2025 年收入增长 72% [S3]；毛利率为 71% [S5]。",
                ),
                table(
                    ("Key Metrics Snapshot", "关键指标概览"),
                    [L("Metric", "指标"), L("Figure", "数值"), L("As of", "截至"), L("Basis", "依据")],
                    [
                        [L("Revenue", "收入"), "$86M", "2025", L("Company figure reported by Reuters [S3].", "路透社报道的公司数据 [S3]。")],
                        [L("Revenue growth", "收入增速"), "72%", "2025", L("Company figure [S3].", "公司数据 [S3]。")],
                        [L("Gross margin", "毛利率"), "71%", "2025", L("Management presentation [S5].", "管理层演示材料 [S5]。")],
                        [L("Storage under management", "管理储能容量"), "9.4 GWh", "2026-06", L("Management presentation [S5].", "管理层演示材料 [S5]。")],
                        [L("Net revenue retention", "净收入留存率"), "138%", "2025", L("Computed from cohort data [C5].", "根据客户群数据计算 [C5]。")],
                        [L("Software margin estimate", "软件利润率估算"), "~55%", L("Undated", "未注明日期"), L("Single practitioner estimate [S13].", "单一从业者估算 [S13]。")],
                    ],
                    component="key_metrics_snapshot",
                ),
                s("company_overview", 2),
                para(
                    "Veltrix raised $62M across three rounds before the Series D [S12]. The Series D was led by a growth fund and priced at $2.4B post-money [S1].",
                    "在 D 轮之前，Veltrix 通过三轮融资共筹集 $62M [S12]。D 轮由一家成长基金领投，投后估值 $2.4B [S1]。",
                ),
                table(
                    ("Deal Terms", "交易条款"),
                    [L("Term", "条款"), L("Detail", "内容")],
                    [
                        [L("Instrument", "工具"), L("Series D preferred stock", "D 轮优先股")],
                        [L("Round size", "融资规模"), "$180M"],
                        [L("Post-money valuation", "投后估值"), "$2.4B"],
                        [L("Liquidation preference", "清算优先权"), L("1x, non-participating", "1 倍，不参与分配")],
                        [L("Proposed amount", "拟投金额"), "[TO BE DETERMINED BY IC]"],
                    ],
                    component="deal_terms",
                ),
                s("company_overview", 3),
                para(
                    "Veltrix signed its first utility in 2021, passed 5 GWh under management in 2024 and added its tenth utility in May 2026 [S10].",
                    "Veltrix 于 2021 年签下第一家公用事业客户，2024 年管理容量突破 5 GWh，并于 2026 年 5 月签下第十家公用事业客户 [S10]。",
                ),
                s("company_overview", 4),
                para(
                    "Proven: retention, multi-vendor deployments and revenue growth. Unproven: pricing power against bundled software and a public-company finance team.",
                    "已验证：客户留存、多品牌部署与收入增长。未验证：面对捆绑软件的定价能力，以及具备上市公司水准的财务团队。",
                ),
            ],
        },
        {
            "id": "market_industry",
            "blocks": [
                s("market_industry", 1),
                para(
                    "Veltrix sits in the software layer between battery hardware and power markets: it earns a fee for every MWh it dispatches.",
                    "Veltrix 位于电池硬件与电力市场之间的软件层：每调度一兆瓦时即收取一笔费用。",
                ),
                s("market_industry", 2),
                para(
                    "The adopted range is a $1.1B serviceable market today, growing to $3.9B by 2030, because only utility-scale storage buys third-party dispatch software.",
                    "本文采用的可服务市场为当前 $1.1B，到 2030 年增长至 $3.9B，因为只有电网级储能会采购第三方调度软件。",
                ),
                table(
                    ("Market Sizing", "市场规模"),
                    [L("Tier", "层级"), L("Definition", "定义"), L("Size today", "当前规模"), L("Size at exit year", "退出年规模"), L("CAGR", "年复合增速"), L("Basis/source", "依据/来源")],
                    [
                        ["TAM", L("All storage software and services", "全部储能软件与服务"), "$4.8B", "$16.0B", "27%", L("IEA deployment path [S7].", "国际能源署部署路径 [S7]。")],
                        ["SAM", L("Utility-scale dispatch software", "电网级调度软件"), "$1.1B", "$3.9B", "29%", L("Wood Mackenzie installs [S8] × fee per MWh.", "伍德麦肯兹装机量 [S8] × 每兆瓦时费用。")],
                        ["SOM", L("US utilities, multi-vendor fleets", "美国公用事业多品牌储能"), "$0.3B", "$1.2B", "32%", L("Our estimate from the SAM and share of multi-vendor fleets.", "基于可服务市场与多品牌储能占比的自行估算。")],
                    ],
                ),
                chart(
                    "grouped_bar",
                    ("Market size today and at exit", "当前与退出年的市场规模"),
                    [
                        {"label": "2026", "points": [{"x": "TAM", "y": 4.8}, {"x": "SAM", "y": 1.1}, {"x": "SOM", "y": 0.3}]},
                        {"label": "2030", "points": [{"x": "TAM", "y": 16.0}, {"x": "SAM", "y": 3.9}, {"x": "SOM", "y": 1.2}]},
                    ],
                    unit=("$B", "十亿美元"),
                    reading=("Higher is bigger; compare each pair of bars.", "越高越大；请成对比较。"),
                    caption=("The serviceable market grows 3.5x by 2030.", "可服务市场到 2030 年增长 3.5 倍。"),
                    source_ids=["S7", "S8"],
                ),
                s("market_industry", 3),
                para(
                    "Utilities need storage to firm solar; installations doubled in 2025 [S8]. Each new site needs dispatch software from its first day.",
                    "公用事业需要储能来平滑光伏出力；2025 年装机量翻倍 [S8]。每个新项目从投运第一天起就需要调度软件。",
                ),
                s("market_industry", 4),
                para(
                    "The market caps Veltrix nearer $20B than $100B of enterprise value: the serviceable market is $3.9B in 2030, and no software vendor holds more than a third of it.",
                    "市场规模将 Veltrix 的企业价值上限限制在接近 $20B 而非 $100B：2030 年可服务市场为 $3.9B，且没有任何软件厂商占据超过三分之一。",
                ),
                s("market_industry", 5),
                para(
                    "FERC Order No. 2023 speeds interconnection from 2027 [S11]; tax credits for storage run to 2032.",
                    "美国联邦能源管理委员会第 2023 号令将从 2027 年起加快并网 [S11]；储能税收抵免持续到 2032 年。",
                ),
                _scorecard_sentence(13, 15),
            ],
        },
        {
            "id": "product_business_model",
            "blocks": [
                s("product_business_model", 1),
                para(
                    "Owners pay because better dispatch earns more in power markets: customers report 8-12% more trading revenue per battery [S15].",
                    "业主付费是因为更好的调度能在电力市场赚取更多收益：客户反馈每块电池的交易收入提高 8-12% [S15]。",
                ),
                s("product_business_model", 2),
                para(
                    "Veltrix charges a fixed fee per MWh under management plus an optimization fee tied to market revenue [S6].",
                    "Veltrix 按管理容量每兆瓦时收取固定费用，外加与市场收益挂钩的优化费用 [S6]。",
                ),
                s("product_business_model", 3),
                table(
                    ("Key Operating Metrics", "关键运营指标"),
                    [L("Metric", "指标"), L("2024", "2024"), L("2025", "2025"), L("Note", "说明")],
                    [
                        [L("GWh under management", "管理容量（GWh）"), "5.1", "8.2", L("Company figure [S5].", "公司数据 [S5]。")],
                        [L("Revenue per MWh", "每兆瓦时收入"), "$10,200", "$10,500", L("Flat price, rising volume.", "价格持平，规模增长。")],
                        [L("Customers", "客户数"), "8", "10", L("Utilities only [S10].", "仅统计公用事业 [S10]。")],
                    ],
                    component="key_operating_metrics",
                ),
                s("product_business_model", 4),
                para(
                    "Revenue is recurring: 84% comes from multi-year contracts [S5], and optimization fees add upside when power prices swing.",
                    "收入具有经常性：84% 来自多年期合同 [S5]，电价波动时优化费用带来额外收益。",
                ),
                s("product_business_model", 5),
                para(
                    "Demand runs both ways: bookings rose 55% in the first half of 2026 [S5], while two renewals came at lower prices [S16].",
                    "需求信号有两面：2026 年上半年订单增长 55% [S5]，但有两份续约价格下降 [S16]。",
                ),
                _scorecard_sentence(7, 10),
            ],
        },
        {
            "id": "competitive_landscape",
            "blocks": [
                s("competitive_landscape", 1),
                para(
                    "Three kinds of players compete: hardware vendors that bundle software, independent optimizers, and utilities building in-house tools.",
                    "竞争者分三类：捆绑软件的硬件厂商、独立优化软件商，以及自建工具的公用事业。",
                ),
                s("competitive_landscape", 2),
                table(
                    ("Competitive Analysis", "竞争分析"),
                    [L("Company", "公司"), L("Model", "模式"), L("Scale", "规模"), L("Where it wins", "优势领域")],
                    [
                        ["Veltrix", L("Independent software", "独立软件"), "9.4 GWh", L("Multi-vendor utility fleets", "多品牌公用事业储能")],
                        ["Tesla Autobidder", L("Bundled with hardware", "随硬件捆绑"), "~40 GWh", L("Single-vendor sites", "单一品牌项目")],
                        ["Fluence Mosaic", L("Bundled with hardware", "随硬件捆绑"), "~25 GWh", L("Fluence-built projects", "Fluence 建设的项目")],
                    ],
                    component="competitive_analysis",
                ),
                chart(
                    "hbar",
                    ("Storage under management", "管理储能容量"),
                    [{"label": "GWh", "points": [{"x": "Tesla Autobidder", "y": 40}, {"x": "Fluence Mosaic", "y": 25}, {"x": "Veltrix", "y": 9.4}]}],
                    unit="GWh",
                    reading=("Longer bars manage more storage.", "条形越长，管理的储能越多。"),
                    caption=("Veltrix is a third the size of the bundled leader.", "Veltrix 的规模约为捆绑领先者的三分之一。"),
                    source_ids=["S9", "S14"],
                ),
                s("competitive_landscape", 3),
                table(
                    ("Replacement vs. Coexistence", "替代还是共存"),
                    [L("Question", "问题"), L("Answer", "判断")],
                    [
                        [L("Does bundled software replace Veltrix?", "捆绑软件会取代 Veltrix 吗？"), L("On single-vendor sites, yes; on mixed fleets, no.", "单一品牌项目会；混合储能不会。")],
                        [L("Can Veltrix coexist with hardware vendors?", "Veltrix 能与硬件厂商共存吗？"), L("Yes, as the neutral layer utilities prefer [S15].", "能，作为公用事业偏好的中立软件层 [S15]。")],
                    ],
                    component="replacement_coexistence",
                ),
                s("competitive_landscape", 4),
                para(
                    "Tesla is number one today by volume; in five years the leader in multi-vendor fleets is likely an independent, and Veltrix is the largest independent now.",
                    "按规模计算，特斯拉目前排名第一；五年后多品牌储能领域的领先者很可能是独立软件商，而 Veltrix 目前是最大的独立厂商。",
                ),
                _scorecard_sentence(9, 15),
            ],
        },
        {
            "id": "moat",
            "blocks": [
                s("moat", 1),
                table(
                    ("Moat Audit", "护城河审计"),
                    [L("Source", "来源"), L("Evidence", "证据"), L("Durability", "持久性")],
                    [
                        [L("Switching cost", "切换成本"), L("Integration with utility control rooms takes 9-12 months [S15].", "与公用事业调度中心的集成需要 9-12 个月 [S15]。"), L("High", "高")],
                        [L("Data", "数据"), L("Four years of dispatch data across 9.4 GWh.", "覆盖 9.4 GWh 的四年调度数据。"), L("Medium", "中")],
                    ],
                    component="moat",
                ),
                s("moat", 2),
                para(
                    "With $5B, a competitor could copy the optimizer in two years, but not the utility integrations, which take a year per customer.",
                    "拥有 $5B 的竞争对手可以在两年内复制优化算法，但无法复制公用事业集成，每个客户需要一年时间。",
                ),
                s("moat", 3),
                para(
                    "The moat is widening on integrations and narrowing on algorithms, as open-source optimizers close the gap.",
                    "护城河在集成方面变宽，在算法方面变窄，因为开源优化工具正在缩小差距。",
                ),
                _scorecard_sentence(10, 15),
            ],
        },
        {
            "id": "financial_analysis",
            "blocks": [
                s("financial_analysis", 1),
                table(
                    ("Revenue Picture", "收入情况"),
                    [L("Fiscal year", "财年"), L("Revenue", "收入"), L("Growth", "增速"), L("Gross margin", "毛利率"), L("Burn", "现金消耗")],
                    [
                        ["2023", "$29M", "81%", "64%", "$38M"],
                        ["2024", "$50M", "72%", "68%", "$31M"],
                        ["2025", "$86M", "72%", "71%", "$24M"],
                    ],
                    component="revenue",
                ),
                s("financial_analysis", 2),
                table(
                    ("Forecast", "业绩预测"),
                    [L("Fiscal year", "财年"), L("Revenue", "收入"), L("Key assumption", "关键假设")],
                    [
                        ["2026E", "$118M", L("Two new utilities [S5].", "新增两家公用事业 [S5]。")],
                        ["2027E", "$170M", L("Retrofit pipeline converts.", "改造项目管线转化。")],
                        ["2028E", "$240M", L("Price holds per MWh.", "每兆瓦时价格保持稳定。")],
                    ],
                ),
                chart(
                    "line",
                    ("Revenue trajectory", "收入轨迹"),
                    [
                        {
                            "label": "Revenue",
                            "points": [
                                {"x": "2023", "y": 29},
                                {"x": "2024", "y": 50},
                                {"x": "2025", "y": 86},
                                {"x": "2026E", "y": 118},
                                {"x": "2027E", "y": 170},
                                {"x": "2028E", "y": 240},
                            ],
                        }
                    ],
                    unit=("$M", "百万美元"),
                    reading=("Actuals to 2025; the rest is the company plan.", "2025 年及以前为实际数，之后为公司计划。"),
                    caption=("Growth slows from 72% to about 40% in the plan.", "计划中增速从 72% 放缓至约 40%。"),
                    source_ids=["S3", "S5"],
                ),
                para(
                    "The plan asks for 2.8x revenue in three years; the best disclosed peer did 2.1x at the same scale [S9].",
                    "计划要求三年内收入增长 2.8 倍；在相同规模下，披露数据最好的可比公司增长了 2.1 倍 [S9]。",
                ),
                s("financial_analysis", 3),
                table(
                    ("Growth Quality", "增长质量"),
                    [L("Measure", "指标"), L("Value", "数值"), L("Reading", "解读")],
                    [
                        [L("Rule of 40", "40 法则"), "44", L("Growth 72% less burn margin 28%.", "增速 72% 减去 28% 的现金消耗率。")],
                        [L("Organic vs acquired growth", "内生与并购增长"), "100% / 0%", L("No acquisitions.", "无并购。")],
                    ],
                    component="growth_bridge",
                ),
                s("financial_analysis", 4),
                para(
                    "Revenue ties to the Form D raise and to three reference customers' invoices [S2, S15].",
                    "收入与 Form D 备案的融资额以及三位受访客户的发票相互印证 [S2, S15]。",
                ),
                s("financial_analysis", 5),
                para(
                    "Growth is getting healthier: burn fell from $38M to $24M while revenue tripled.",
                    "增长更加健康：收入增长两倍的同时，现金消耗从 $38M 降至 $24M。",
                ),
                _scorecard_sentence(12, 15),
            ],
        },
        {
            "id": "team_governance",
            "blocks": [
                s("team_governance", 1),
                para(
                    "The founder is a former grid operator engineer; the CFO joined from a public utility in 2024 [S12].",
                    "创始人曾是电网调度工程师；首席财务官于 2024 年从一家上市公用事业公司加入 [S12]。",
                ),
                s("team_governance", 2),
                table(
                    ("Board of Directors", "董事会"),
                    [L("Seat", "席位"), L("Holder", "成员"), L("Strategic value", "战略价值")],
                    [
                        [L("Founder", "创始人"), L("Founder and CEO", "创始人兼首席执行官"), L("Product and sales", "产品与销售")],
                        [L("Investor", "投资人"), L("Series D lead", "D 轮领投方"), L("IPO preparation", "上市准备")],
                        [L("Independent", "独立董事"), L("Audit chair, added 2026", "审计委员会主席，2026 年加入"), L("Controls", "内控")],
                    ],
                    component="board",
                ),
                s("team_governance", 3),
                para("The founder has built dispatch systems for ten years.", "创始人拥有十年调度系统开发经验。"),
                s("team_governance", 4),
                para(
                    "The founder still owns product and sales, a dependence the risk section rates 4/10.",
                    "创始人仍同时负责产品和销售，风险部分将这一依赖评为 4/10。",
                ),
                s("team_governance", 5),
                para(
                    "Readiness is partial: an audit chair is in place, a public-company controller is not.",
                    "上市准备度部分到位：审计委员会主席已就位，但上市公司水准的财务总监尚未到位。",
                ),
                _scorecard_sentence(6, 10),
            ],
        },
        {
            "id": "valuation",
            "blocks": [
                s("valuation", 1),
                table(
                    ("Comparables", "可比公司"),
                    [L("Company", "公司"), L("Revenue", "收入"), L("Growth", "增速"), L("Multiple", "倍数"), L("Growth-adjusted multiple", "增长调整倍数"), L("Note", "说明")],
                    [
                        [L("Veltrix (entry)", "Veltrix（入场）"), "$86M", "72%", "27.9x", "0.39", L("Series D price [C1].", "D 轮价格 [C1]。")],
                        ["Fluence", "$2.7B", "18%", "1.6x", "0.09", L("Hardware-heavy [S9].", "以硬件为主 [S9]。")],
                        [L("Software peer set", "软件可比组"), "$300M", "35%", "11x", "0.31", L("Median of four [S4].", "四家公司中位数 [S4]。")],
                    ],
                ),
                chart(
                    "bar",
                    ("Revenue multiples", "收入倍数"),
                    [{"label": "EV / revenue", "points": [{"x": "Veltrix (entry)", "y": 27.9}, {"x": "Software peer set", "y": 11}, {"x": "Fluence", "y": 1.6}]}],
                    unit=("x revenue", "收入倍数"),
                    reading=("Higher bars are more expensive.", "柱子越高越贵。"),
                    caption=("Veltrix enters at 2.5x the software median.", "Veltrix 的入场倍数是软件公司中位数的 2.5 倍。"),
                    source_ids=["S4", "S9"],
                ),
                s("valuation", 2),
                table(
                    ("Valuation Methods", "估值方法"),
                    [L("Method", "方法"), L("Result or range", "结果或区间"), L("Basis", "依据"), L("Why trusted or not", "可信度")],
                    [
                        [L("Comparable companies", "可比公司法"), "$0.9B–$1.4B", L("11x–16x 2025 revenue [S4].", "2025 年收入的 11–16 倍 [S4]。"), L("Trusted: listed peers.", "可信：上市可比公司。")],
                        [L("Precedent transactions", "先例交易法"), "$1.2B–$1.8B", L("Two 2025 software takeovers [S4].", "2025 年两起软件收购 [S4]。"), L("Partly: small sample.", "部分可信：样本较少。")],
                        [L("DCF / earnings power", "现金流折现法"), "$1.5B", L("2030 plan at 25% margin.", "按 2030 年计划及 25% 利润率。"), L("Weak: rests on the plan.", "较弱：依赖公司计划。")],
                    ],
                ),
                s("valuation", 3),
                table(
                    ("Time-Base Integrity", "估值时点核查"),
                    [L("Figure", "数据"), L("Date", "日期"), L("Used as", "用途")],
                    [
                        [L("Post-money $2.4B", "投后估值 $2.4B"), "2026-08", L("Entry price [S1].", "入场价格 [S1]。")],
                        [L("Peer multiples", "可比倍数"), "2026-07", L("Exit multiple anchor [S4].", "退出倍数锚点 [S4]。")],
                    ],
                    component="time_base_integrity",
                ),
                s("valuation", 4),
                para(
                    "The price assumes revenue of about $420M in 2030 at a 10x multiple, which is the whole company plan [C2].",
                    "该价格假设 2030 年收入约 $420M、倍数为 10 倍，即公司计划的全部 [C2]。",
                ),
                s("valuation", 5),
                para(
                    "Fair value is $1.4B–$1.8B; the top end needs the plan, the bottom end only needs today's growth to halve.",
                    "公允价值为 $1.4B–$1.8B；上端需要计划兑现，下端只要求当前增速减半。",
                ),
                _scorecard_sentence(3, 10),
            ],
        },
        {
            "id": "returns_exit",
            "blocks": [
                s("returns_exit", 1),
                table(
                    ("Scenario Analysis", "情景分析"),
                    [
                        L("Scenario", "情景"), L("Exit year", "退出年份"), L("Exit-year revenue", "退出年收入"), L("Exit multiple", "退出倍数"),
                        L("Exit valuation", "退出估值"), L("Dilution assumption", "稀释假设"), L("Value to this round", "本轮所得价值"),
                        L("Gross MOIC", "总回报倍数"), L("IRR", "内部收益率"),
                    ],
                    [
                        [L("Bear", "悲观"), "2030", "$210M", "6x", "$1.26B", "15%", "$1.07B", "0.45x [C3]", "-16%"],
                        [L("Base", "基准"), "2030", "$420M", "10x", "$4.2B", "15%", "$3.57B", "1.5x [C2]", "9%"],
                        [L("Bull", "乐观"), "2030", "$640M", "12x", "$7.68B", "15%", "$6.53B", "2.7x [C4]", "25%"],
                    ],
                    component="scenario_analysis",
                ),
                chart(
                    "bar",
                    ("Gross MOIC by scenario", "各情景总回报倍数"),
                    [
                        {
                            "label": L("Gross MOIC", "总回报倍数"),
                            "points": [
                                {"x": L("Bear", "悲观"), "y": 0.45},
                                {"x": L("Base", "基准"), "y": 1.5},
                                {"x": L("Bull", "乐观"), "y": 2.7},
                            ],
                        }
                    ],
                    unit=("x capital", "资本倍数"),
                    reading=("Bars below 1.0x lose money.", "低于 1.0 倍的柱子意味着亏损。"),
                    caption=("Only the bull case clears 2x.", "只有乐观情形超过 2 倍。"),
                    source_ids=["S4", "S5"],
                    reference_lines=[{"y": 1.0, "label": L("1.0x: capital back", "1.0 倍：收回本金")}],
                ),
                s("returns_exit", 2),
                para(
                    "Growth of 4.9x times a 0.36x multiple factor gives the base 1.5x [C6]; the return goes to zero only if the exit multiple falls below 1x revenue.",
                    "4.9 倍的增长乘以 0.36 倍的倍数因子，得出基准情形 1.5 倍 [C6]；只有退出倍数跌破 1 倍收入，回报才会归零。",
                ),
                chart(
                    "bar",
                    ("Return decomposition (base case)", "回报分解（基准情形）"),
                    [{"label": "Factor", "points": [{"x": "Growth factor", "y": 4.88}, {"x": "Multiple factor", "y": 0.36}, {"x": "Base MOIC", "y": 1.49}]}],
                    unit=("x", "倍"),
                    reading=("Factors multiply to the base MOIC.", "各因子相乘得到基准回报倍数。"),
                    caption=("The multiple gives back most of the growth.", "倍数收缩抵消了大部分增长。"),
                    source_ids=["S5"],
                ),
                s("returns_exit", 3),
                table(
                    ("Exit Map", "退出路径"),
                    [L("Route", "路径"), "2027", "2028", "2029", "2030"],
                    [
                        [L("IPO", "上市"), L("Not ready; low", "未就绪；低"), L("Partly ready; low", "部分就绪；低"), L("Ready; medium", "就绪；中"), L("Ready; medium", "就绪；中")],
                        [L("M&A", "并购"), L("Possible; low", "可能；低"), L("Possible; medium", "可能；中"), L("Likely; medium", "较可能；中"), L("Likely; medium", "较可能；中")],
                        [L("Secondary", "老股转让"), L("Thin; low", "流动性差；低"), L("Thin; low", "流动性差；低"), L("Some; medium", "有一定流动性；中"), L("Some; medium", "有一定流动性；中")],
                    ],
                ),
                s("returns_exit", 4),
                table(
                    ("Catalyst Timeline", "催化剂时间线"),
                    [L("Date", "日期"), L("Catalyst", "催化剂"), L("Effect", "影响")],
                    [
                        ["2026-12", L("Two utility renewals", "两家公用事业续约"), L("Confirms retention", "确认客户留存")],
                        ["2027-06", L("First audited year as a large filer", "首个大型申报公司审计年度"), L("Opens the IPO window", "打开上市窗口")],
                    ],
                ),
                s("returns_exit", 5),
                para(
                    "The return is a growth bet: the multiple falls from 27.9x to 10x, so everything rests on revenue.",
                    "这笔回报押注的是增长：倍数从 27.9 倍降至 10 倍，因此一切取决于收入。",
                ),
                _scorecard_sentence(2, 5),
            ],
        },
        {
            "id": "investment_risk",
            "blocks": [
                s("investment_risk", 1),
                para(
                    "The risks concentrate on price: at 27.9x revenue, every other risk works through the exit multiple [C1].",
                    "风险集中在价格上：以 27.9 倍收入入场，其他所有风险都通过退出倍数传导 [C1]。",
                ),
                s("investment_risk", 2),
                *[block for number, (title, rows) in enumerate(RISK_CARDS, start=1) for block in _risk_card(number, title, rows)],
                s("investment_risk", 3),
                {
                    "type": "bullets",
                    "component": "disconfirming_evidence",
                    "items": [
                        L(
                            "Two 2026 renewals came at lower prices per MWh, the first sign of pricing pressure [S16].",
                            "2026 年有两份续约的每兆瓦时价格下降，这是定价压力的第一个信号 [S16]。",
                        ),
                        L(
                            "A practitioner estimates software margins nearer 55% than the reported 71% [S13].",
                            "一位从业者估计软件利润率接近 55%，而非公司报告的 71% [S13]。",
                        ),
                    ],
                },
                s("investment_risk", 4),
                para(
                    "In the downside the plan slips two years and the multiple falls to 6x: the round returns 0.45x [C3]. The risk verdict is high, driven by price.",
                    "在下行情景中，计划推迟两年且倍数降至 6 倍：本轮回报 0.45 倍 [C3]。风险结论为高，主要由价格驱动。",
                ),
                _scorecard_sentence(2, 5),
            ],
        },
        {
            "id": "investment_decision",
            "blocks": [
                s("investment_decision", 1),
                table(
                    ("Evidence Thresholds — The Six Questions", "证据门槛——六个关键问题"),
                    [L("Question", "问题"), L("Answer", "回答"), L("Basis", "依据")],
                    [
                        [L("Is the market big enough to matter?", "市场是否足够大？"), L("Yes", "是"), L("$3.9B serviceable market by 2030 [S8].", "到 2030 年可服务市场 $3.9B [S8]。")],
                        [L("Is the company top-1-3 with evidence?", "公司是否有证据位列前三？"), L("Qualified", "有条件"), L("Largest independent, third overall.", "最大的独立厂商，整体第三。")],
                        [L("Does the moat survive success?", "护城河能否经受成功考验？"), L("Qualified", "有条件"), L("Integrations yes, algorithms no.", "集成可以，算法不行。")],
                        [L("Is the growth real and healthy?", "增长是否真实健康？"), L("Yes", "是"), L("72% growth with falling burn [S3].", "增长 72% 且现金消耗下降 [S3]。")],
                        [L("Does the price leave a return?", "价格是否留有回报空间？"), L("No", "否"), L("Base case 1.5x [C2].", "基准情形 1.5 倍 [C2]。")],
                        [L("Can we get our money out?", "资金能否退出？"), L("Qualified", "有条件"), L("IPO from 2029; M&A possible.", "2029 年起可上市；并购可能。")],
                    ],
                    component="evidence_thresholds",
                ),
                para(
                    "The price question flips to Yes at or below $1.6B post-money, where the base case returns 2.2x.",
                    "当投后估值不高于 $1.6B、基准情形回报达到 2.2 倍时，价格问题的答案将变为“是”。",
                ),
                s("investment_decision", 2),
                table(
                    ("Scorecard", "评分卡"),
                    [L("Dimension", "维度"), L("Weight", "权重"), L("Score", "得分"), L("Why", "理由")],
                    [
                        [L("Market size & growth", "市场空间与增速"), "15", "13", L("Fast-growing serviceable market.", "可服务市场增长快。")],
                        [L("Industry position", "行业地位"), "15", "9", L("Largest independent, third overall.", "最大的独立厂商，整体第三。")],
                        [L("Moat", "护城河"), "15", "10", L("Integrations hold; algorithms do not.", "集成壁垒稳固，算法壁垒不足。")],
                        [L("Revenue growth & quality", "收入增长与质量"), "15", "12", L("72% growth, 138% retention.", "增长 72%，留存率 138%。")],
                        [L("Business model & unit economics", "商业模式与单位经济"), "10", "7", L("Recurring fees, price pressure.", "经常性收费，价格承压。")],
                        [L("Team & governance", "团队与治理"), "10", "6", L("Thin bench before a listing.", "上市前管理梯队偏薄。")],
                        [L("Valuation", "估值"), "10", "3", L("27.9x revenue.", "27.9 倍收入。")],
                        [L("Exit certainty", "退出确定性"), "5", "2", L("IPO not before 2029.", "2029 年前无法上市。")],
                        [L("Risk/reward", "风险收益比"), "5", "2", L("Bear case loses half.", "悲观情形亏损一半。")],
                        [L("Total", "合计"), "100", "68", L("Watch list (70-79 = watch; below 70 = pass).", "观察名单（70-79 为观察；低于 70 为放弃）。")],
                    ],
                ),
                s("investment_decision", 3),
                {
                    "type": "bullets",
                    "items": [
                        L("What is demonstrated: 72% revenue growth with falling burn [S3].", "已证明：收入增长 72% 且现金消耗下降 [S3]。"),
                        L("What is demonstrated: 138% net revenue retention [C5].", "已证明：净收入留存率 138% [C5]。"),
                        L("What remains unresolved: pricing power against bundled software.", "尚未解决：面对捆绑软件的定价能力。"),
                        L("What remains unresolved: a public-company finance team.", "尚未解决：具备上市公司水准的财务团队。"),
                    ],
                },
                s("investment_decision", 4),
                {
                    "type": "callout",
                    "component": "investment_decision",
                    "title": L("Investment decision", "投资决定"),
                    "body": L(
                        "Recommendation: pass at $2.4B; BSH commits only at or below $1.6B post-money, where the base case returns 2.2x. Proposed amount: [TO BE DETERMINED BY IC]. Allocation: [TO BE DETERMINED BY IC].",
                        "投资建议：在 $2.4B 估值下放弃；仅当投后估值不高于 $1.6B、基准情形回报达到 2.2 倍时，BSH 才出资。拟投金额：[TO BE DETERMINED BY IC]。配置比例：[TO BE DETERMINED BY IC]。",
                    ),
                },
                para(
                    "Not an offer to sell securities; terms are governed by definitive subscription documents.",
                    "本文件并非证券出售要约；条款以最终认购文件为准。",
                    component="disclosures",
                ),
                s("investment_decision", 5),
                table(
                    ("What changes the verdict", "改变结论的条件"),
                    [L("Indicator", "指标"), L("Current value", "当前值"), L("Trigger threshold", "触发阈值"), L("Response if triggered", "触发后的应对")],
                    [
                        [L("Post-money valuation", "投后估值"), "$2.4B", "≤ $1.6B", L("Re-open the decision.", "重新评估投资决定。")],
                        [L("Revenue per MWh", "每兆瓦时收入"), "$10,500", "< $9,000", L("Lower the fair value.", "下调公允价值。")],
                        [L("Top-three revenue share", "前三大客户收入占比"), "50%", "> 60%", L("Raise the concentration rating.", "上调集中度风险评级。")],
                    ],
                ),
            ],
        },
    ]
    return {
        "schema_version": 1,
        "structure": V2.meta(),
        "company": copy.deepcopy(COMPANY),
        "run": copy.deepcopy(RUN),
        "sections": sections,
        "sources": copy.deepcopy(SOURCES),
        "calculations": copy.deepcopy(CALCULATIONS),
    }


# ---- late compact (seven sections) -------------------------------------------------


def late_compact_package() -> dict:
    s = lambda sid, n: _sub(COMPACT, sid, n)  # noqa: E731
    full = late_v2_package()
    by_id = {section["id"]: section for section in full["sections"]}

    def blocks_of(section_id: str, *, skip_headings: bool = True) -> list[dict]:
        return [
            copy.deepcopy(block)
            for block in by_id[section_id]["blocks"]
            if not (skip_headings and block.get("type") == "heading" and block.get("level") == 2)
        ]

    exec_blocks = []
    exec_number = 0
    for block in by_id["executive_summary"]["blocks"]:
        if block.get("type") == "heading":
            exec_number += 1
            exec_blocks.append(s("executive_summary", exec_number))
        else:
            exec_blocks.append(copy.deepcopy(block))

    overview = by_id["company_overview"]["blocks"]
    risk_blocks = [
        block
        for number, (title, rows) in enumerate(RISK_CARDS[:5], start=1)
        for block in _risk_card(number, title, rows)
    ]
    sections = [
        {"id": "executive_summary", "blocks": exec_blocks},
        {
            "id": "company_team",
            "blocks": [
                s("company_team", 1),
                copy.deepcopy(overview[1]),
                copy.deepcopy(overview[2]),
                s("company_team", 2),
                copy.deepcopy(overview[4]),
                copy.deepcopy(overview[5]),
                s("company_team", 3),
                para(
                    "The founder has built dispatch systems for ten years; the CFO joined from a public utility in 2024 [S12].",
                    "创始人拥有十年调度系统开发经验；首席财务官于 2024 年从一家上市公用事业公司加入 [S12]。",
                ),
                _scorecard_sentence(6, 10),
            ],
        },
        {
            "id": "thesis_market",
            "blocks": [
                s("thesis_market", 1),
                para(
                    "Utilities need storage to firm solar, and installations doubled in 2025 [S8]; each new site needs dispatch software from its first day.",
                    "公用事业需要储能来平滑光伏出力，2025 年装机量翻倍 [S8]；每个新项目从投运第一天起就需要调度软件。",
                ),
                s("thesis_market", 2),
                *[copy.deepcopy(b) for b in by_id["market_industry"]["blocks"] if b.get("type") in {"table", "chart"}],
                s("thesis_market", 3),
                copy.deepcopy(by_id["competitive_landscape"]["blocks"][3]),
                para(
                    "Integrations take a year per utility, which protects the installed base even as algorithms commoditize.",
                    "每家公用事业的集成需要一年，即使算法趋于同质化，这也能保护已有客户。",
                ),
                _scorecard_sentence(13, 15),
                _scorecard_sentence(9, 15),
                _scorecard_sentence(10, 15),
            ],
        },
        {
            "id": "business_financials",
            "blocks": [
                s("business_financials", 1),
                para(
                    "Veltrix charges a fixed fee per MWh under management plus an optimization fee tied to market revenue [S6].",
                    "Veltrix 按管理容量每兆瓦时收取固定费用，外加与市场收益挂钩的优化费用 [S6]。",
                ),
                s("business_financials", 2),
                copy.deepcopy(by_id["financial_analysis"]["blocks"][1]),
                copy.deepcopy(by_id["financial_analysis"]["blocks"][4]),
                s("business_financials", 3),
                para(
                    "Growth is getting healthier: burn fell from $38M to $24M while revenue tripled.",
                    "增长更加健康：收入增长两倍的同时，现金消耗从 $38M 降至 $24M。",
                ),
                _scorecard_sentence(7, 10),
                _scorecard_sentence(12, 15),
            ],
        },
        {
            "id": "valuation_returns",
            "blocks": [
                s("valuation_returns", 1),
                para(
                    "The price assumes revenue of about $420M in 2030 at a 10x multiple, which is the whole company plan [C1, C2].",
                    "该价格假设 2030 年收入约 $420M、倍数为 10 倍，即公司计划的全部 [C1, C2]。",
                ),
                s("valuation_returns", 2),
                copy.deepcopy(by_id["returns_exit"]["blocks"][1]),
                copy.deepcopy(by_id["returns_exit"]["blocks"][2]),
                s("valuation_returns", 3),
                para(
                    "An IPO is possible from 2029; a strategic sale to a hardware vendor is the likelier route before then.",
                    "2029 年起可以上市；在此之前，出售给硬件厂商是更可能的退出路径。",
                ),
                _scorecard_sentence(3, 10),
                _scorecard_sentence(2, 5),
            ],
        },
        {
            "id": "risks",
            "blocks": [
                s("risks", 1),
                copy.deepcopy(by_id["investment_risk"]["blocks"][1]),
                s("risks", 2),
                *risk_blocks,
                s("risks", 3),
                copy.deepcopy(
                    next(b for b in by_id["investment_risk"]["blocks"] if b.get("component") == "disconfirming_evidence")
                ),
                _scorecard_sentence(2, 5),
            ],
        },
        {
            "id": "investment_decision",
            "blocks": [
                s("investment_decision", 1),
                copy.deepcopy(next(b for b in by_id["investment_decision"]["blocks"] if b.get("type") == "table" and "Scorecard" == b["title"]["en"])),
                s("investment_decision", 2),
                copy.deepcopy(next(b for b in by_id["investment_decision"]["blocks"] if b.get("component") == "evidence_thresholds")),
                s("investment_decision", 3),
                copy.deepcopy(next(b for b in by_id["investment_decision"]["blocks"] if b.get("component") == "investment_decision")),
                copy.deepcopy(next(b for b in by_id["investment_decision"]["blocks"] if b.get("component") == "disclosures")),
                s("investment_decision", 4),
                copy.deepcopy(by_id["investment_decision"]["blocks"][-1]),
            ],
        },
    ]
    return {
        "schema_version": 1,
        "structure": COMPACT.meta(),
        "company": copy.deepcopy(COMPANY),
        "run": copy.deepcopy(RUN),
        "sections": sections,
        "sources": copy.deepcopy(SOURCES),
        "calculations": copy.deepcopy(CALCULATIONS),
    }
