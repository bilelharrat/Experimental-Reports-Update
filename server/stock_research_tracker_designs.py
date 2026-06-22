"""Default stock-research tracker designs and source seeds."""
from __future__ import annotations

STARTER_TRACKERS: list[dict] = [
    {
        "id": "us-macro",
        "type": "macro",
        "display_name": "US Macro Tracker",
        "owner": "Research",
        "priority": 1,
        "market": "United States",
        "country": "US",
        "sector": "Macro",
        "cadence": {"frequency": "weekly", "event_driven": True},
        "output_languages": ["en", "zh"],
        "objective": (
            "Identify the macro regime, rate-path changes, liquidity shifts, and "
            "cross-asset moves that change equity risk appetite or sector leadership."
        ),
        "research_questions": [
            {
                "question": "Did inflation, labor, growth, or Fed communication change the expected policy path?",
                "decision_use": "Sets the risk-on/risk-off backdrop for all equity trackers.",
            },
            {
                "question": "Which rates, USD, credit, or commodity moves create direct read-through for covered themes?",
                "decision_use": "Separates macro noise from investable sector pressure points.",
            },
            {
                "question": "What scheduled macro catalysts can invalidate current weekly signals?",
                "decision_use": "Feeds trigger conditions and Hypothesis Lab windows.",
            },
        ],
        "signal_categories": [
            {"name": "policy_path", "examples": ["FOMC statement", "SEP dots", "Fed speakers"]},
            {"name": "inflation_growth_mix", "examples": ["CPI", "PPI", "PCE", "retail sales", "GDP"]},
            {"name": "market_transmission", "examples": ["2Y/10Y yields", "DXY", "credit spreads", "sector ETFs"]},
            {"name": "liquidity_and_fiscal", "examples": ["Treasury issuance", "TGA/RRP", "budget deadlines"]},
        ],
        "metric_watchlist": [
            {"name": "Fed funds target range", "unit": "percent", "source_preference": "Federal Reserve"},
            {"name": "Core CPI / PCE trend", "unit": "percent y/y and m/m", "source_preference": "BLS/BEA"},
            {"name": "Initial jobless claims", "unit": "claims", "source_preference": "Department of Labor"},
            {"name": "2Y/10Y Treasury yield and curve change", "unit": "basis points", "source_preference": "U.S. Treasury/FRED"},
            {"name": "S&P 500 sector and factor leadership", "unit": "weekly return", "source_preference": "primary market data"},
        ],
        "catalyst_rules": [
            {"event": "FOMC or Powell remarks", "action": "Always produce policy-path and equity-duration read-through."},
            {"event": "CPI/PCE release", "action": "Compare headline/core and key components against prior and consensus if available."},
            {"event": "Payrolls or claims shock", "action": "Flag soft-landing, recession, or inflation-risk implication."},
        ],
        "hypothesis_templates": [
            {
                "template": "If yields fall after a benign inflation/labor print, long-duration AI/software signals should outrank cyclicals for one week.",
                "horizon": "1-2 weeks",
            },
            {
                "template": "If inflation reaccelerates and 10Y yields rise, valuation-sensitive AI beneficiaries should show weaker forward returns.",
                "horizon": "1-4 weeks",
            },
        ],
        "source_requirements": [
            {"tier": "primary", "requirement": "Fed, BLS, BEA, Census, Treasury, DOL, or FRED data for every macro datapoint."},
            {"tier": "secondary", "requirement": "Market wrap or sell-side note only for interpretation, never as sole data source."},
        ],
    },
    {
        "id": "ai-cloud-infrastructure",
        "type": "industry",
        "display_name": "AI Cloud Infrastructure",
        "owner": "Research",
        "priority": 1,
        "market": "Global",
        "country": "US",
        "sector": "Technology",
        "industry": "AI infrastructure",
        "subsegments": ["accelerators", "cloud capex", "networking", "HBM", "AI data centers"],
        "tickers": ["NVDA", "AMD", "AVGO", "ANET", "SMCI", "DELL"],
        "cadence": {"frequency": "weekly", "event_driven": True},
        "output_languages": ["en", "zh"],
        "objective": (
            "Track the AI infrastructure value chain from accelerator demand to "
            "networking, memory, servers, and data-center deployment constraints."
        ),
        "research_questions": [
            {
                "question": "Is AI accelerator demand still rising faster than supply and installed capacity?",
                "decision_use": "Determines whether the capex cycle remains expansionary.",
            },
            {
                "question": "Where are bottlenecks shifting across GPUs, networking, HBM, power, and systems integration?",
                "decision_use": "Identifies second-order beneficiaries and margin-risk nodes.",
            },
            {
                "question": "Are customer mix, pricing, or product transitions changing revenue durability?",
                "decision_use": "Feeds company-specific risk/reward for NVDA, AMD, AVGO, ANET, SMCI, and DELL.",
            },
        ],
        "signal_categories": [
            {"name": "accelerator_cycle", "examples": ["GPU lead times", "new platform ramps", "supply allocation"]},
            {"name": "networking_attach", "examples": ["Ethernet/InfiniBand", "switch silicon", "optics"]},
            {"name": "memory_and_packaging", "examples": ["HBM capacity", "advanced packaging", "substrates"]},
            {"name": "systems_and_deployment", "examples": ["server backlog", "rack-scale integration", "data-center readiness"]},
        ],
        "metric_watchlist": [
            {"name": "Data center revenue growth", "unit": "percent y/y", "source_preference": "company earnings"},
            {"name": "AI-related backlog/orders", "unit": "dollars or qualitative", "source_preference": "company earnings/transcripts"},
            {"name": "Gross margin bridge", "unit": "basis points", "source_preference": "company filings"},
            {"name": "Capex pull-through", "unit": "dollars", "source_preference": "hyperscaler disclosures"},
        ],
        "catalyst_rules": [
            {"event": "NVIDIA/AMD/Broadcom earnings", "action": "Extract demand, supply, margin, and product-transition read-through."},
            {"event": "Hyperscaler capex update", "action": "Map spending changes to accelerator, networking, and server suppliers."},
            {"event": "Supply-chain warning", "action": "Separate demand weakness from capacity/timing constraint."},
        ],
        "hypothesis_templates": [
            {
                "template": "If hyperscaler capex guidance rises and networking suppliers confirm order acceleration, AI infrastructure breadth should improve beyond NVDA.",
                "horizon": "2-6 weeks",
            },
            {
                "template": "If server/integration names guide below AI demand commentary, margin or execution risk is becoming the binding constraint.",
                "horizon": "1-4 weeks",
            },
        ],
        "source_requirements": [
            {"tier": "primary", "requirement": "At least one company disclosure or SEC filing for each issuer-level claim."},
            {"tier": "confirming", "requirement": "Use supply-chain or vertical media only to confirm timing, not as sole financial evidence."},
        ],
    },
    {
        "id": "hyperscaler-capex",
        "type": "industry",
        "display_name": "Hyperscaler AI Capex",
        "owner": "Research",
        "priority": 1,
        "market": "United States",
        "country": "US",
        "sector": "Technology",
        "industry": "Cloud platforms",
        "subsegments": ["AI capex", "cloud growth", "GPU clusters", "data center leasing"],
        "tickers": ["MSFT", "AMZN", "GOOGL", "META", "ORCL"],
        "cadence": {"frequency": "weekly", "event_driven": True},
        "output_languages": ["en", "zh"],
        "objective": (
            "Track cloud and AI capex commitments from the largest platform buyers "
            "and translate them into demand durability for the infrastructure stack."
        ),
        "research_questions": [
            {
                "question": "Are capex budgets being raised, delayed, or reallocated across compute, networking, and real estate?",
                "decision_use": "Anchors demand for AI infrastructure suppliers.",
            },
            {
                "question": "Is cloud revenue growth accelerating enough to justify AI infrastructure spend?",
                "decision_use": "Separates productive capex from speculative overbuild risk.",
            },
            {
                "question": "Which platform is changing the industry spend curve or supplier allocation?",
                "decision_use": "Feeds ticker-specific read-through and hypothesis generation.",
            },
        ],
        "signal_categories": [
            {"name": "capex_revision", "examples": ["annual capex guide", "lease commitments", "PP&E additions"]},
            {"name": "cloud_revenue_quality", "examples": ["Azure", "AWS", "Google Cloud", "OCI"]},
            {"name": "monetization", "examples": ["AI services revenue", "backlog", "customer adoption"]},
            {"name": "capacity_constraint", "examples": ["data center availability", "power", "GPU supply"]},
        ],
        "metric_watchlist": [
            {"name": "Capital expenditures", "unit": "dollars", "source_preference": "cash flow statement/earnings release"},
            {"name": "Cloud revenue growth", "unit": "percent y/y", "source_preference": "segment disclosure"},
            {"name": "Remaining performance obligation/backlog", "unit": "dollars", "source_preference": "10-Q/earnings release"},
            {"name": "Finance lease and purchase commitments", "unit": "dollars", "source_preference": "SEC filings"},
        ],
        "catalyst_rules": [
            {"event": "Mega-cap platform earnings", "action": "Extract capex, cloud growth, AI monetization, and supplier commentary."},
            {"event": "Datacenter leasing or power update", "action": "Flag whether constraint extends or slows capex deployment."},
        ],
        "hypothesis_templates": [
            {
                "template": "If two or more hyperscalers raise capex while cloud revenue accelerates, AI infrastructure suppliers should receive positive estimate-revision pressure.",
                "horizon": "2-8 weeks",
            },
            {
                "template": "If capex rises while cloud growth decelerates, market should penalize platform free-cash-flow durability.",
                "horizon": "1-6 weeks",
            },
        ],
        "source_requirements": [
            {"tier": "primary", "requirement": "Use company earnings releases, 10-Q/10-K, or transcripts for capex and cloud metrics."},
            {"tier": "cross-check", "requirement": "Tie supplier read-through back to AI Cloud Infrastructure tracker outputs."},
        ],
    },
    {
        "id": "nvidia",
        "type": "company",
        "display_name": "NVIDIA",
        "owner": "Research",
        "priority": 1,
        "market": "United States",
        "country": "US",
        "sector": "Technology",
        "industry": "Semiconductors",
        "tickers": ["NVDA"],
        "cadence": {"frequency": "weekly", "event_driven": True},
        "output_languages": ["en", "zh"],
        "objective": (
            "Maintain a source-backed view on NVIDIA estimate revisions, data-center "
            "demand durability, product transitions, margin risk, and valuation triggers."
        ),
        "research_questions": [
            {
                "question": "Are data-center revenue, backlog, and customer commitments still beating expectations?",
                "decision_use": "Primary driver of earnings revision and thesis strength.",
            },
            {
                "question": "Do product transitions, supply limits, export controls, or competition threaten gross margin or shipment timing?",
                "decision_use": "Identifies downside triggers before they appear in consensus.",
            },
            {
                "question": "What concrete event would change the rating from monitor/add/trim?",
                "decision_use": "Forces actionable trigger discipline.",
            },
        ],
        "signal_categories": [
            {"name": "data_center_demand", "examples": ["accelerator revenue", "customer mix", "backlog"]},
            {"name": "platform_transition", "examples": ["Blackwell/Rubin ramps", "networking attach", "software"]},
            {"name": "margin_and_supply", "examples": ["COGS", "HBM", "packaging", "export controls"]},
            {"name": "valuation_and_positioning", "examples": ["estimate revisions", "multiple risk", "crowding"]},
        ],
        "metric_watchlist": [
            {"name": "Data Center revenue", "unit": "dollars and percent y/y", "source_preference": "earnings release"},
            {"name": "Gross margin", "unit": "percent", "source_preference": "earnings release/10-Q"},
            {"name": "Inventory and purchase obligations", "unit": "dollars", "source_preference": "10-Q/10-K"},
            {"name": "Share repurchase/dividend changes", "unit": "dollars", "source_preference": "earnings release"},
        ],
        "catalyst_rules": [
            {"event": "Quarterly earnings", "action": "Produce estimate-revision, margin, and product-ramp read-through."},
            {"event": "Product launch or export-control update", "action": "Map to revenue timing, customer mix, and margin."},
        ],
        "hypothesis_templates": [
            {
                "template": "If NVIDIA data-center revenue and gross margin both beat while capex trackers remain positive, NVDA should retain leadership over the next earnings-revision window.",
                "horizon": "2-6 weeks",
            },
            {
                "template": "If revenue beats but margin guidance falls on transition/supply costs, the stock should underperform broader AI infrastructure peers.",
                "horizon": "1-4 weeks",
            },
        ],
        "source_requirements": [
            {"tier": "primary", "requirement": "Use NVIDIA earnings materials, SEC filings, and event transcripts for all company claims."},
            {"tier": "confirming", "requirement": "Use supply-chain/media claims only when supported by official disclosures or clearly marked as unconfirmed."},
        ],
    },
    {
        "id": "data-center-power-grid",
        "type": "industry",
        "display_name": "Data Center Power And Grid",
        "owner": "Research",
        "priority": 2,
        "market": "United States",
        "country": "US",
        "sector": "Industrials / Utilities",
        "industry": "Power infrastructure",
        "subsegments": ["grid equipment", "backup power", "cooling", "nuclear", "gas turbines"],
        "tickers": ["ETN", "VRT", "GEV", "CEG", "NEE", "PWR"],
        "cadence": {"frequency": "weekly", "event_driven": True},
        "output_languages": ["en", "zh"],
        "objective": (
            "Track whether AI data-center electricity demand is creating durable "
            "order growth, pricing power, or bottlenecks in grid, power, cooling, and generation assets."
        ),
        "research_questions": [
            {
                "question": "Are data-center orders/backlog translating into revenue and margin for power equipment suppliers?",
                "decision_use": "Identifies real beneficiaries versus narrative exposure.",
            },
            {
                "question": "Are utilities, nuclear owners, and gas/power equipment suppliers seeing credible incremental demand?",
                "decision_use": "Maps AI demand into generation and grid investment.",
            },
            {
                "question": "Where do permitting, interconnection, or power availability slow AI deployment?",
                "decision_use": "Feeds constraint risks back into AI infrastructure trackers.",
            },
        ],
        "signal_categories": [
            {"name": "equipment_orders", "examples": ["switchgear", "transformers", "UPS", "thermal"]},
            {"name": "generation_and_ppas", "examples": ["nuclear", "gas turbines", "renewables", "PPAs"]},
            {"name": "grid_constraint", "examples": ["interconnection queues", "transmission", "permitting"]},
            {"name": "margin_capacity", "examples": ["backlog conversion", "pricing", "capacity expansion"]},
        ],
        "metric_watchlist": [
            {"name": "Electrical/data-center order growth", "unit": "percent y/y", "source_preference": "company earnings"},
            {"name": "Backlog and book-to-bill", "unit": "ratio/dollars", "source_preference": "company earnings"},
            {"name": "Utility load growth guidance", "unit": "percent or MW/GW", "source_preference": "utility filings"},
            {"name": "Power price and capacity market signals", "unit": "dollars/MWh", "source_preference": "EIA/FERC/market data"},
        ],
        "catalyst_rules": [
            {"event": "Power equipment earnings", "action": "Separate AI/data-center order contribution from general electrification."},
            {"event": "Utility load or PPA announcement", "action": "Assess credibility, timing, and counterparty concentration."},
        ],
        "hypothesis_templates": [
            {
                "template": "If equipment backlog grows faster than revenue with stable margins, power infrastructure names should keep estimate support.",
                "horizon": "1-2 quarters",
            },
            {
                "template": "If power availability becomes the binding AI data-center constraint, infrastructure suppliers and nuclear/gas beneficiaries should outrank server assemblers.",
                "horizon": "1-3 months",
            },
        ],
        "source_requirements": [
            {"tier": "primary", "requirement": "Use company disclosures, utility filings, EIA/FERC data, and official grid/operator data."},
            {"tier": "secondary", "requirement": "Use project media as timing evidence only when sponsor/customer is clear."},
        ],
    },
    {
        "id": "enterprise-ai-software",
        "type": "industry",
        "display_name": "Enterprise AI Software",
        "owner": "Research",
        "priority": 2,
        "market": "United States",
        "country": "US",
        "sector": "Technology",
        "industry": "Software",
        "subsegments": ["AI agents", "data platforms", "workflow automation", "enterprise search"],
        "tickers": ["MSFT", "CRM", "NOW", "SNOW", "PLTR", "DDOG"],
        "cadence": {"frequency": "weekly", "event_driven": True},
        "output_languages": ["en", "zh"],
        "objective": (
            "Determine which enterprise software companies are converting AI product "
            "narratives into measurable bookings, retention, usage, or margin expansion."
        ),
        "research_questions": [
            {
                "question": "Which vendors disclose AI revenue, attach rates, usage, or customer expansions?",
                "decision_use": "Separates monetization evidence from marketing claims.",
            },
            {
                "question": "Are AI features improving growth or merely increasing compute and R&D cost?",
                "decision_use": "Tests margin durability and FCF quality.",
            },
            {
                "question": "Where are platform shifts causing share gains or displacement risk?",
                "decision_use": "Feeds long/short software hypotheses.",
            },
        ],
        "signal_categories": [
            {"name": "monetization", "examples": ["AI ARR", "seat attach", "consumption growth"]},
            {"name": "customer_adoption", "examples": ["large deals", "net retention", "case studies"]},
            {"name": "cost_to_serve", "examples": ["gross margin", "compute cost", "R&D"]},
            {"name": "platform_competition", "examples": ["agent ecosystems", "data gravity", "workflow lock-in"]},
        ],
        "metric_watchlist": [
            {"name": "Current RPO / backlog growth", "unit": "percent y/y", "source_preference": "earnings release/10-Q"},
            {"name": "Subscription/product revenue growth", "unit": "percent y/y", "source_preference": "earnings release"},
            {"name": "Net retention or large customer count", "unit": "percent/count", "source_preference": "company disclosure"},
            {"name": "Gross margin and FCF margin", "unit": "percent", "source_preference": "earnings release"},
        ],
        "catalyst_rules": [
            {"event": "Software earnings", "action": "Extract AI-specific monetization and compare to base business growth."},
            {"event": "Product/platform launch", "action": "Mark as narrative until adoption or pricing evidence appears."},
        ],
        "hypothesis_templates": [
            {
                "template": "If AI-specific adoption is disclosed alongside accelerating RPO, the vendor should receive positive estimate-revision support.",
                "horizon": "1-2 quarters",
            },
            {
                "template": "If AI announcements do not improve growth metrics and margins compress, AI narrative premium should fade.",
                "horizon": "1-3 months",
            },
        ],
        "source_requirements": [
            {"tier": "primary", "requirement": "Use earnings materials and SEC filings for growth, RPO, margin, and customer metrics."},
            {"tier": "product", "requirement": "Use product announcements only for feature availability; do not infer revenue without financial evidence."},
        ],
    },
    {
        "id": "defense-autonomy",
        "type": "industry",
        "display_name": "Defense Autonomy And Space",
        "owner": "Research",
        "priority": 2,
        "market": "United States",
        "country": "US",
        "sector": "Industrials",
        "industry": "Defense technology",
        "subsegments": ["autonomous systems", "space", "C4ISR", "drones", "defense software"],
        "tickers": ["PLTR", "LMT", "RTX", "NOC", "KTOS", "RKLB"],
        "cadence": {"frequency": "weekly", "event_driven": True},
        "output_languages": ["en", "zh"],
        "objective": (
            "Track budget, contract, and earnings evidence for autonomy, defense AI, "
            "space systems, drones, and C4ISR modernization across listed defense names."
        ),
        "research_questions": [
            {
                "question": "Which contract awards or budget lines show real spend toward autonomy, space, and AI-enabled defense?",
                "decision_use": "Distinguishes funded programs from defense-tech narrative.",
            },
            {
                "question": "Are listed suppliers converting awards into backlog, revenue, and margin?",
                "decision_use": "Links government demand to investable earnings impact.",
            },
            {
                "question": "Are program delays, protests, budget fights, or fixed-price overruns changing risk?",
                "decision_use": "Flags negative catalysts before earnings misses.",
            },
        ],
        "signal_categories": [
            {"name": "contract_awards", "examples": ["DoD daily contracts", "OTA awards", "SDA/NASA awards"]},
            {"name": "budget_and_policy", "examples": ["appropriations", "FY budget books", "service priorities"]},
            {"name": "program_execution", "examples": ["backlog conversion", "launch cadence", "cost overruns"]},
            {"name": "software_autonomy", "examples": ["AI targeting", "C4ISR", "mission software"]},
        ],
        "metric_watchlist": [
            {"name": "Contract award value by ticker/program", "unit": "dollars", "source_preference": "DoD/USAspending"},
            {"name": "Backlog and book-to-bill", "unit": "dollars/ratio", "source_preference": "company earnings"},
            {"name": "Segment sales and operating margin", "unit": "dollars/percent", "source_preference": "company filings"},
            {"name": "Launches, deliveries, or program milestones", "unit": "count/date", "source_preference": "company/government disclosure"},
        ],
        "catalyst_rules": [
            {"event": "DoD contract award", "action": "Map prime/sub exposure, value, duration, and whether it is incremental."},
            {"event": "Defense earnings", "action": "Compare backlog, book-to-bill, margins, and program commentary."},
            {"event": "Budget/appropriation event", "action": "Identify winners, losers, timing risk, and unfunded mandate risk."},
        ],
        "hypothesis_templates": [
            {
                "template": "If autonomy/space awards cluster around a supplier and backlog conversion improves, that supplier should outperform traditional primes.",
                "horizon": "1-3 months",
            },
            {
                "template": "If awards rise but margins compress or program delays increase, revenue growth should not translate into equity outperformance.",
                "horizon": "1-2 quarters",
            },
        ],
        "source_requirements": [
            {"tier": "primary", "requirement": "Use DoD/USAspending/NASA/SDA or company filings for contract and budget claims."},
            {"tier": "secondary", "requirement": "Use media only to contextualize program intent or competitive positioning."},
        ],
    },
    {
        "id": "palantir",
        "type": "company",
        "display_name": "Palantir Technologies",
        "owner": "Research",
        "priority": 2,
        "market": "United States",
        "country": "US",
        "sector": "Technology",
        "industry": "Software",
        "tickers": ["PLTR"],
        "cadence": {"frequency": "weekly", "event_driven": True},
        "output_languages": ["en", "zh"],
        "objective": (
            "Maintain a source-backed view on Palantir growth durability, AIP adoption, "
            "government/commercial mix, margin quality, contract momentum, and valuation risk."
        ),
        "research_questions": [
            {
                "question": "Is AIP driving measurable commercial revenue acceleration or only anecdotal customer interest?",
                "decision_use": "Tests the core growth thesis.",
            },
            {
                "question": "Are government awards broadening, renewing, or concentrating risk?",
                "decision_use": "Assesses durability of the government revenue base.",
            },
            {
                "question": "Do margins and SBC support the valuation implied by growth?",
                "decision_use": "Flags add/trim triggers.",
            },
        ],
        "signal_categories": [
            {"name": "commercial_aip", "examples": ["US commercial revenue", "customer count", "AIP bootcamps"]},
            {"name": "government_contracts", "examples": ["DoD awards", "renewals", "international government"]},
            {"name": "margin_quality", "examples": ["adjusted operating margin", "GAAP profitability", "SBC"]},
            {"name": "valuation_and_crowding", "examples": ["multiple expansion", "estimate revisions", "short interest"]},
        ],
        "metric_watchlist": [
            {"name": "US commercial revenue growth", "unit": "percent y/y", "source_preference": "earnings release"},
            {"name": "Remaining deal value / RPO", "unit": "dollars", "source_preference": "10-Q/10-K"},
            {"name": "Customer count and net dollar retention", "unit": "count/percent", "source_preference": "earnings materials"},
            {"name": "Adjusted operating margin and free cash flow margin", "unit": "percent", "source_preference": "earnings release"},
        ],
        "catalyst_rules": [
            {"event": "Quarterly earnings", "action": "Extract growth, AIP evidence, margin, and guide changes."},
            {"event": "Material government award", "action": "Map award value, duration, agency, and whether it is new or renewal."},
        ],
        "hypothesis_templates": [
            {
                "template": "If US commercial growth and customer count accelerate with stable margins, PLTR should retain premium growth positioning.",
                "horizon": "1-2 quarters",
            },
            {
                "template": "If growth remains strong but deal value concentration rises or margins deteriorate, valuation risk should dominate the signal.",
                "horizon": "1-3 months",
            },
        ],
        "source_requirements": [
            {"tier": "primary", "requirement": "Use Palantir earnings materials, SEC filings, and contract award sources for all material claims."},
            {"tier": "confirming", "requirement": "Use product pages and customer stories only to contextualize AIP, not as revenue proof."},
        ],
    },
]


STARTER_TRACKER_SOURCES: dict[str, list[dict]] = {
    "us-macro": [
        {
            "title": "Federal Reserve FOMC meeting calendars, statements, minutes, and SEP links",
            "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            "priority": "official",
            "relevance": "monetary_policy",
            "notes": "Primary source for FOMC dates, statements, minutes, implementation notes, press conferences, and Summary of Economic Projections.",
        },
        {
            "title": "BLS Consumer Price Index latest release",
            "url": "https://www.bls.gov/news.release/cpi.nr0.htm",
            "priority": "primary_data",
            "relevance": "inflation",
            "notes": "Primary CPI source. Use headline/core m/m and y/y, components, release date, and next release date.",
        },
        {
            "title": "BLS Producer Price Index latest release",
            "url": "https://www.bls.gov/news.release/ppi.nr0.htm",
            "priority": "primary_data",
            "relevance": "inflation",
            "notes": "Primary PPI source. Use final demand, core measures, goods/services detail, and revisions.",
        },
        {
            "title": "BEA release schedule and national accounts releases",
            "url": "https://www.bea.gov/news/schedule",
            "priority": "primary_data",
            "relevance": "growth",
            "notes": "Primary source for GDP, PCE, personal income, and related release timing.",
        },
        {
            "title": "U.S. Treasury interest-rate data",
            "url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
            "priority": "primary_data",
            "relevance": "rates",
            "notes": "Primary Treasury yield curve source. Use 2Y, 10Y, 30Y levels and weekly change.",
        },
        {
            "title": "Department of Labor unemployment insurance weekly claims data",
            "url": "https://www.dol.gov/agencies/eta/ui-data",
            "priority": "primary_data",
            "relevance": "labor",
            "notes": "Primary source for weekly initial and continuing unemployment claims.",
        },
        {
            "title": "Census Bureau advance monthly retail sales",
            "url": "https://www.census.gov/retail/sales.html",
            "priority": "primary_data",
            "relevance": "growth",
            "notes": "Primary source for retail sales and revisions.",
        },
    ],
    "ai-cloud-infrastructure": [
        {
            "title": "NVIDIA financial reports and quarterly results",
            "url": "https://investor.nvidia.com/financial-info/financial-reports/default.aspx",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use data-center revenue, product-transition commentary, gross margin, shareholder return, and latest results.",
        },
        {
            "title": "Advanced Micro Devices quarterly results",
            "url": "https://ir.amd.com/financial-information/quarterly-results",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use datacenter segment revenue, MI-series commentary, gross margin, and guidance.",
        },
        {
            "title": "Broadcom quarterly results",
            "url": "https://investors.broadcom.com/financial-information/quarterly-results",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use AI networking/custom silicon revenue, backlog, and margin commentary.",
        },
        {
            "title": "Arista Networks quarterly results",
            "url": "https://investors.arista.com/financials/quarterly-results/default.aspx",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use cloud titan demand, AI ethernet, customer concentration, and guidance.",
        },
        {
            "title": "Dell Technologies quarterly results",
            "url": "https://investors.delltechnologies.com/financial-information/quarterly-results/default.aspx",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use AI server orders, backlog, ISG revenue, margin, and cash conversion.",
        },
        {
            "title": "Super Micro Computer SEC filings",
            "url": "https://ir.supermicro.com/financials/sec-filings/default.aspx",
            "priority": "sec_filing",
            "relevance": "filings",
            "notes": "Use filings for server revenue, margins, working capital, accounting risk, and customer/supplier disclosures.",
        },
    ],
    "hyperscaler-capex": [
        {
            "title": "Microsoft investor relations earnings",
            "url": "https://www.microsoft.com/en-us/investor/default",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use Azure growth, AI demand, capital expenditures, lease commitments, and management commentary.",
        },
        {
            "title": "Amazon quarterly results",
            "url": "https://ir.aboutamazon.com/quarterly-results/default.aspx",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use AWS growth, capex, operating margin, fulfillment versus AI infrastructure spending, and guidance.",
        },
        {
            "title": "Alphabet investor relations",
            "url": "https://abc.xyz/investor/",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use Google Cloud growth, capex, AI infrastructure comments, and free cash flow.",
        },
        {
            "title": "Meta quarterly earnings",
            "url": "https://investor.atmeta.com/financials/",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use capex guide, AI infrastructure spend, revenue growth, and management comments on compute needs.",
        },
        {
            "title": "Oracle quarterly results",
            "url": "https://investor.oracle.com/financials/quarterly-results/default.aspx",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use OCI growth, remaining performance obligations, capex, cloud demand, and data-center capacity commentary.",
        },
    ],
    "nvidia": [
        {
            "title": "NVIDIA quarterly results",
            "url": "https://investor.nvidia.com/financial-info/quarterly-results/default.aspx",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Primary earnings source for revenue, segment performance, gross margin, guidance, shareholder returns, and management commentary.",
        },
        {
            "title": "NVIDIA financial reports",
            "url": "https://investor.nvidia.com/financial-info/financial-reports/default.aspx",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use latest financial results and archived releases for trend comparisons.",
        },
        {
            "title": "NVIDIA SEC filings",
            "url": "https://investor.nvidia.com/financial-info/sec-filings/default.aspx",
            "priority": "sec_filing",
            "relevance": "filings",
            "notes": "Primary source for 10-Q/10-K risk factors, revenue detail, inventory, commitments, and legal/regulatory disclosures.",
        },
        {
            "title": "SEC submissions feed for NVIDIA",
            "url": "https://data.sec.gov/submissions/CIK0001045810.json",
            "priority": "sec_filing",
            "relevance": "filings",
            "notes": "Machine-readable SEC submissions feed for latest NVIDIA filings.",
        },
        {
            "title": "NVIDIA events and presentations",
            "url": "https://investor.nvidia.com/events-and-presentations/events-and-presentations/default.aspx",
            "priority": "investor_presentation",
            "relevance": "management_commentary",
            "notes": "Use investor events, presentations, and conference materials for product-cycle and demand commentary.",
        },
    ],
    "data-center-power-grid": [
        {
            "title": "Eaton investor relations and quarterly earnings",
            "url": "https://www.eaton.com/us/en-us/company/investor-relations/financial-presentations-webcasts.html",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use electrical segment orders, backlog, data-center commentary, margins, and guidance.",
        },
        {
            "title": "Vertiv quarterly results",
            "url": "https://investors.vertiv.com/financials/quarterly-results/default.aspx",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use organic orders, backlog, thermal/power data-center demand, and full-year guidance.",
        },
        {
            "title": "GE Vernova reports and filings",
            "url": "https://www.gevernova.com/investors/reports-filings",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use gas power, electrification, grid solutions, backlog, and margin commentary.",
        },
        {
            "title": "Constellation Energy events and presentations",
            "url": "https://investors.constellationenergy.com/events-and-presentations/past-events/",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use nuclear fleet, PPA, load growth, and data-center power demand commentary.",
        },
        {
            "title": "EIA electricity data",
            "url": "https://www.eia.gov/electricity/",
            "priority": "primary_data",
            "relevance": "power_data",
            "notes": "Use electricity generation, demand, prices, and fuel mix data as primary context.",
        },
        {
            "title": "FERC electric industry data",
            "url": "https://www.ferc.gov/industries-data/electric",
            "priority": "primary_data",
            "relevance": "grid_data",
            "notes": "Use for transmission, reliability, market, and regulatory context.",
        },
    ],
    "enterprise-ai-software": [
        {
            "title": "Microsoft investor relations earnings",
            "url": "https://www.microsoft.com/en-us/investor/default",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use Copilot, Azure AI, cloud growth, margin, and AI monetization commentary.",
        },
        {
            "title": "Salesforce quarterly results",
            "url": "https://investor.salesforce.com/financials/quarterly-results/",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use Data Cloud, Agentforce, subscription growth, RPO, margin, and guidance.",
        },
        {
            "title": "ServiceNow financial performance",
            "url": "https://investor.servicenow.com/financial-resources/financial-performance/default.aspx",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use subscription revenue, cRPO, workflow AI adoption, customer metrics, and margin.",
        },
        {
            "title": "Snowflake quarterly results",
            "url": "https://investors.snowflake.com/financials/quarterly-results/default.aspx",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use product revenue, consumption, RPO, customer counts, data/AI workloads, and margin.",
        },
        {
            "title": "Palantir quarterly results",
            "url": "https://investors.palantir.com/financials/quarterly-results",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use AIP adoption, US commercial growth, government growth, deal value, and margins.",
        },
        {
            "title": "Datadog quarterly results",
            "url": "https://investors.datadoghq.com/financials/quarterly-results/default.aspx",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use observability/security platform growth, AI workload commentary, large customers, and margin.",
        },
    ],
    "defense-autonomy": [
        {
            "title": "Department of Defense daily contract awards",
            "url": "https://www.defense.gov/News/Contracts/",
            "priority": "official",
            "relevance": "contract_awards",
            "notes": "Primary source for daily U.S. defense contract awards, values, agencies, contractors, and program names.",
        },
        {
            "title": "USAspending federal awards search",
            "url": "https://www.usaspending.gov/search",
            "priority": "primary_data",
            "relevance": "contract_awards",
            "notes": "Primary federal award data source for contract validation and recipient/program cross-checks.",
        },
        {
            "title": "Lockheed Martin investor relations",
            "url": "https://investors.lockheedmartin.com/",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use sales, backlog, cash flow, program commentary, and guidance.",
        },
        {
            "title": "RTX investor relations events and presentations",
            "url": "https://investors.rtx.com/events-and-presentations",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use segment sales, backlog, GTF/program risk, defense demand, and guidance.",
        },
        {
            "title": "Northrop Grumman quarterly earnings archive",
            "url": "https://investor.northropgrumman.com/financial-information/quarterly-earnings",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use Space, Mission Systems, Aeronautics, backlog, margin, and program commentary.",
        },
        {
            "title": "Kratos investor relations",
            "url": "https://ir.kratosdefense.com/",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use unmanned systems, defense software/hardware, bookings, book-to-bill, and guidance.",
        },
        {
            "title": "Rocket Lab quarterly results",
            "url": "https://investors.rocketlabcorp.com/financial-information/quarterly-results",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Use launch cadence, space systems backlog, government awards, margin, and guidance.",
        },
    ],
    "palantir": [
        {
            "title": "Palantir quarterly results",
            "url": "https://investors.palantir.com/financials/quarterly-results",
            "priority": "company_disclosure",
            "relevance": "earnings",
            "notes": "Primary earnings source for revenue, US commercial growth, government growth, margins, customer count, and guidance.",
        },
        {
            "title": "Palantir SEC filings",
            "url": "https://investors.palantir.com/financials/sec-filings",
            "priority": "sec_filing",
            "relevance": "filings",
            "notes": "Primary filing source for 10-Q/10-K details, risk factors, remaining deal value, SBC, and customer concentration.",
        },
        {
            "title": "SEC submissions feed for Palantir",
            "url": "https://data.sec.gov/submissions/CIK0001321655.json",
            "priority": "sec_filing",
            "relevance": "filings",
            "notes": "Machine-readable SEC submissions feed for latest Palantir filings.",
        },
        {
            "title": "Palantir investor news",
            "url": "https://investors.palantir.com/news",
            "priority": "company_press_release",
            "relevance": "company_news",
            "notes": "Use company press releases for major contracts, product news, and investor updates.",
        },
        {
            "title": "Palantir AIP platform page",
            "url": "https://www.palantir.com/platforms/aip/",
            "priority": "official",
            "relevance": "product",
            "notes": "Use for product capability context only; do not infer revenue without financial disclosure.",
        },
        {
            "title": "Department of Defense daily contract awards",
            "url": "https://www.defense.gov/News/Contracts/",
            "priority": "official",
            "relevance": "contract_awards",
            "notes": "Use for government award validation and program-level contract details.",
        },
    ],
}
