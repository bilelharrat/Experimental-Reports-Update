---
name: bsh-hormuz-appendix-v3
description: "Generate the BSH V3 bilingual geopolitical / macro-risk parallel appendix for the Strait of Hormuz daily research. From one or more source daily reports for a target date (plus the previous day's reports as a calibration baseline) it produces FOUR files: a Simplified-Chinese Markdown appendix and a Chinese A4 PDF rendered from it, then an English Markdown translation and an English A4 PDF rendered from it. The Chinese Markdown is the single source of truth; the English is a faithful translation of it. Use whenever asked to build, refresh, or regenerate the Hormuz V3 appendix for a given date."
---

# BSH Hormuz V3 Parallel Appendix (Bilingual, Audit-First, Markdown-Sourced)

## Purpose

You produce a **decision-grade, auditable parallel appendix** for the Strait of
Hormuz / Middle East daily risk report. You do **not** rewrite the main report.
You read the raw source report(s) for the target date (and the previous day's
report(s) as a calibration baseline) and emit a stable, machine-readable
Simplified-Chinese Markdown appendix, render it to a Chinese PDF, then translate
the Chinese Markdown into an English Markdown and render that to an English PDF.

This skill runs **two phases in one session**:

- **Phase 1** — generate the Chinese V3 appendix Markdown, then its PDF.
- **Phase 2** — translate the Chinese Markdown to English Markdown, then its PDF.

The Chinese Markdown is the **single authoritative source**. The Chinese PDF
must be rendered from the Chinese Markdown. The English Markdown must be a
faithful translation of the Chinese Markdown. The English PDF must be rendered
from the English Markdown. Do not paste full report bodies into the chat — you
must write files.

---

## I/O contract (filled in by the run header above this skill)

The operational header prepended to this skill for each run gives you the
concrete absolute paths. In general:

- **Run folder (your CWD):** date-keyed output folder. All four output files
  go directly in it.
- **TARGET_DATE:** `YYYY-MM-DD` — the appendix date.
- **SOURCE_REPORTS:** the source file(s) for `TARGET_DATE` (PDF / Markdown /
  text). Read them as the *current* day.
- **PREVIOUS_REPORTS:** the source file(s) for the most recent prior date, if
  any. Use them only as the *previous* baseline for probability deltas and
  calibration. If absent, treat all probabilities as new and say so.
- **DATE_RANGE:** human range string for the document header.
- **OUTPUT_BASENAME_CN** e.g. `v3_appendix_cn_2026_05_15`
- **OUTPUT_BASENAME_EN** e.g. `v3_appendix_en_2026_05_15`

You must create exactly these four files in the run folder:

1. `{OUTPUT_BASENAME_CN}.md`
2. `{OUTPUT_BASENAME_CN}.pdf`
3. `{OUTPUT_BASENAME_EN}.md`
4. `{OUTPUT_BASENAME_EN}.pdf`

Read source PDFs with the `markitdown` Bash tool if available, otherwise
`pandoc`, otherwise the Read tool. Read multi-day inputs in date order and
clearly separate 前日 / 当日 / 校准用后续报告.

================================================================
PHASE 1 — 生成中文 V3 并行附录（Markdown → PDF）
================================================================

你是一个"地缘政治 / 宏观风险日报"的并行附录生成器。

你的任务不是重写主报告，而是基于输入的多日原始报告，生成一份可审计、可校准、可翻译、可用于决策的中文附录，并输出两个文件：

1. 中文 Markdown 文件：`{OUTPUT_BASENAME_CN}.md`
2. 由该 Markdown 文件渲染生成的中文 PDF 文件：`{OUTPUT_BASENAME_CN}.pdf`

Markdown 文件必须作为唯一源文件，PDF 必须由该 Markdown 渲染而来。后续英文版将从这个中文 Markdown 翻译生成，因此 Markdown 结构必须稳定、清晰、可机器读取。

### 输入

- SOURCE_REPORTS：当日一份或多份日报。
- TARGET_DATE：目标附录日期。
- PREVIOUS_REPORTS：前日报告，用于回测和校准（可能为空）。
- OUTPUT_BASENAME：`{OUTPUT_BASENAME_CN}`
- USER_FOCUS：可选，用户特别关注的方向（见运行头）。

按日期顺序读取，明确区分：前日报告 / 当日报告 / 可用于校准的后续报告。

### 核心目标

改善：来源纪律、概率纪律、风险评分透明度、市场含义解释、预测校准、证据门槛、后续英文翻译可复用性。

### 基本原则

1. 不重写主报告。
2. 不把原报告中的说法自动视为事实。
3. 不编造来源、链接、引文、数据或官方确认。
4. 所有重要事实必须进入"来源与验证登记表"。
5. 所有概率必须有定义、时间窗口、置信度、触发条件和下调条件。
6. 明确区分：输入中引用的官方来源说法 / 输入中引用的媒体报道 / 输入中引用的市场数据 / 原报告内部模型输出 / 模型推断 / 推测性判断。
7. 不得把"选择性通行"与"商业化正常通行"混为一谈。
8. 不得把"库存被摧毁"与"已部署风险被清除"混为一谈。
9. 不得把"市场上涨"直接解释为"风险消失"。
10. 如果报告提出"市场隐含概率"，但没有公式、假设和输入数据，必须标记为"不可审计"。
11. 所有前瞻预测必须可以用二元结果评分，即 Brier-score ready。
12. 输出必须是简体中文。
13. 语气应为机构级、克制、可审计、可执行。
14. 不提供投资建议。可以分析市场影响，但必须避免直接交易指令式表达。

### 置信度尺度

- 极高：85-95%
- 高：70-85%
- 中：50-70%
- 低：30-50%
- 极低：<30%

不要使用单点精确置信度，除非它来自原报告中的明确模型概率；即使如此也应优先使用区间。

### 来源敏感度评分

对所有关键 claim 赋予：影响程度（低/中/高）、验证风险（低/中/高）、来源敏感度（低/中/高/关键）。
若同时满足"高影响"且"中等或高验证风险"，标记为"关键"。

### 必须生成的附录结构

文件开头必须包含：

```
# V3 并行附录：决策、证据、预测与市场纪律

- 目标日期：{TARGET_DATE}
- 输入报告范围：{DATE_RANGE}
- 输出语言：简体中文
- 版本：V3-CN
- 说明：本附录为研究用途，不构成投资建议。输入报告中的来源说法未必已被独立核验，除非明确标注。
```

随后依次包含以下章节（标题与列名必须稳定，便于后续英文翻译）：

#### A. 执行决策简报
最多 5 条要点，必须包括：操作性底线 / 最大变化 / 不应过度解读的内容 / 决定性观察点 / 最高置信度的风险错配或市场错配。直接、短、可执行；每条与后文表格或证据对应。

#### B. 来源与验证登记表
表格列：`| ID | Claim | 输入中引用的来源 | Claim 类型 | 验证状态 | 置信度 | 影响程度 | 验证风险 | 来源敏感度 | 证据缺口 |`
ID 使用 `S1, S2, S3 …`。
Claim 类型只能用：输入中引用的官方来源说法 / 输入中引用的媒体报道 / 输入中引用的市场数据 / 原报告内部模型输出 / 模型推断 / 推测性判断。
验证状态只能用：仅由输入支持 / 需要一手来源核验 / 需要市场数据刷新 / 需要独立交叉验证 / 矛盾 / 未解决。

#### C. 矛盾与非等价关系登记表
表格列：`| Claim | 不等于 / 不意味着 | 为什么重要 | 改变判断所需证据 |`
至少检查：军事能力被削弱 ≠ 战争风险归零；水雷库存被摧毁 ≠ 航道已清除；单一船只通行 ≠ 商业通航恢复；一方外交 readout 提及某议题 ≠ 双方达成执行机制；股市上涨 ≠ 地缘风险消失；AI 板块上涨 ≠ 工业供应链风险解除。

#### D. 定义受控的概率仪表盘
使用稳定事件 ID。表格列：`| 事件 ID | 事件定义 | 当前概率 | 前值概率 | 变化 | 时间窗口 | 定义是否变化 | 置信度 | 上调触发器 | 下调触发器 |`
必须拆分 H1 与 H2，不得合并：
- H1：霍尔木兹选择性通行扩大 — 除已知特殊个案外，至少一个新的国家/船东/货主类别获得实际通行。
- H2：霍尔木兹广泛商业化正常通行恢复 — 连续多日可观察的商业通行恢复，并伴随保险/战争险费率明显回落。
必须包含但不限于：D1 外交渠道产生实质性伊朗/霍尔木兹成果；D2 停火崩溃/大规模打击恢复；D3 以色列-黎巴嫩停火崩溃；H1；H2；D4 通胀/利率路径转鹰；D5 海湾国家报复循环；D6 胡塞/曼德海峡升级。原报告未出现的事件标记"新增事件"。前值概率取自 PREVIOUS_REPORTS；若无前值，写"N/A（无前日基线）"。

#### E. 风险评分仪表盘
固定五类：1 军事冲突 2 能源供给 3 贸易通道/航运/保险 4 金融传导 5 石化/工业供应链。
表格列：`| 类别 | 短期评分 | 中期评分 | 趋势 | 评分依据 | 改变评分所需最低证据 |`
默认短期权重：军事 0.35 / 能源 0.20 / 航运 0.25 / 金融 0.10 / 石化 0.10。
默认中期权重：军事 0.15 / 能源 0.35 / 航运 0.15 / 金融 0.20 / 石化 0.15。
必须展示加权计算过程并给出短期与中期总分（保留一位小数再取整）。若与原报告不同，必须说明差异原因。

#### F. 概率依赖矩阵
表格列：`| 事件组合 | 关系 | 方向 | 为什么重要 |`
关系类型：正相关 / 负相关 / 条件依赖 / 弱相关 / 不相关 / 暂无证据。
必须检查：外交突破 与 霍尔木兹通行；军事升级 与 Brent 风险溢价；黎巴嫩升级 与 胡塞/曼德海峡风险；霍尔木兹恢复 与 通胀/利率风险；股市上涨 与 尾部保护价值；选择性通行 与 日韩台供应链压力。

#### G. 市场隐含概率审计
表格列：`| Claim | 是否有公式 | 输入是否足够 | 是否可审计 | 处理方式 |`
无公式/假设/输入数据，不得当作事实；可保留为"模型解释"或"方向性判断"；必须说明不可审计原因。

#### H. 简洁结果导向情景
仅 3 个主要情景 + 1 个尾部情景桶。表格列：`| 情景 | 概率 | 触发条件 | 结果 | 市场影响 | 证伪条件 |`
情景概率合计 100%（除非明确说明非互斥）。不写长篇叙述；每个情景有触发与证伪条件；市场影响给区间或方向，但不得伪装为投资建议。

#### I. 市场与资产矩阵
必须拆分（有数据才列）：Brent、WTI、黄金、SPX、KOSPI、TAIEX、美债 10Y、DXY、JKM LNG，及其他输入中显著资产。
表格列：`| 资产 / 市场 | 当前水平 | 时间戳 / 输入来源 | 预期区间 | 偏向 | 置信度 | 主要驱动 | 证伪条件 |`
说明盘中/收盘/估算；可能过时标"需刷新"；不得混用不同时间戳而不说明。

#### J. 预测校准日志
表格列：`| 预测 ID | 预测 | 概率 | 解决窗口 | 解决规则 | 实际结果 | 结果 | Brier 分数 | 校准说明 |`
预测 ID 用 `CAL-1, CAL-2 …`。不得在解决窗口结束前提前关闭；预测须可二元评分；未解决写"待定"+Brier"N/A"；可用后续/前日报告回测则填实际结果；部分命中须解释。
Brier：p 为预测概率，事件发生分数=(1-p)^2，未发生=p^2。末尾给已解决预测平均 Brier，并注明样本量小的限制。

#### K. 前瞻预测
表格列：`| 预测 ID | 预测 | 概率 | 到期日 | 二元解决规则 |`
预测 ID 用 `FWD-1, FWD-2 …`；至少 5 条；每条未来可明确判定 0/1；每条有日期或明确窗口；不写无法验证的宏大判断。

#### L. 红队注记
3-5 条此附录可能错误的原因，至少包括：来源风险 / 市场数据过时风险 / 概率相关性风险 / 模型过度解释风险 / 未观测事件风险。

#### M. 下一周期数据请求
列出下一次附录最需要补充的具体数据（如：官方 readout 原文、CENTCOM 证词原文、AIS 航运数据、Lloyd's 或战争险报价、黎巴嫩谈判结果、主要指数收盘价/VIX/期权偏斜、BLS/IEA 一手链接）。必须具体，不要泛泛。

### Markdown 格式要求

1. 清晰标题层级：`#` 主标题，`##` 一级章节，`###` 二级章节。
2. 所有表格为标准 Markdown 表格；列名稳定，便于英文翻译；不使用嵌套表格。
3. 不使用会破坏 PDF 渲染的特殊字符。
4. 数字与资产符号用半角/英文：Brent、WTI、SPX、KOSPI、TAIEX、DXY、JKM LNG、美债 10Y。
5. 可用中文标点，避免过长句。
6. 所有日期用 `YYYY-MM-DD`。

写完 `{OUTPUT_BASENAME_CN}.md` 后，按下方"PDF 渲染配方"生成 `{OUTPUT_BASENAME_CN}.pdf` 并做渲染检查。检查通过后再进入 Phase 2。

================================================================
PHASE 2 — Translate the Chinese Markdown into English (Markdown → PDF)
================================================================

You are translating and reproducing the Chinese V3 risk appendix into English.
The Chinese Markdown (`{OUTPUT_BASENAME_CN}.md`) is the **authoritative source**.
Do not reinterpret the analysis unless the Chinese text is ambiguous. Preserve
structure, tables, event IDs, forecast IDs, probabilities, dates, confidence
bands, and calculation logic.

Create:

1. `{OUTPUT_BASENAME_EN}.md`
2. `{OUTPUT_BASENAME_EN}.pdf` (rendered from the English Markdown)

### Translation rules

1. Preserve all section structure, in this order:
   - A. Executive Decision Brief
   - B. Source and Verification Register
   - C. Contradiction and Non-Equivalence Ledger
   - D. Definition-Controlled Probability Dashboard
   - E. Risk Score Dashboard
   - F. Probability Dependency Matrix
   - G. Market-Implied Probability Audit
   - H. Concise Outcome Scenarios
   - I. Market and Asset Matrix
   - J. Forecast Calibration Log
   - K. Forward Forecasts
   - L. Red-Team Notes
   - M. Next-Cycle Data Requests
2. Preserve all IDs: S1, S2, S3 …; D1, D2, H1, H2 …; CAL-1 …; FWD-1 …
3. Preserve all probabilities and numeric values exactly. If a typo is
   suspected, do not silently correct it; add a short translator note.
4. Confidence bands: 极高→Very High, 高→High, 中→Medium, 低→Low, 极低→Very Low.
5. Verification status: 仅由输入支持→Supported by input only; 需要一手来源核验→
   Needs primary-source verification; 需要市场数据刷新→Needs market-data refresh;
   需要独立交叉验证→Needs independent corroboration; 矛盾 / 未解决→
   Contradicted / unresolved.
6. Preserve analytical caution — do not make claims stronger in English.
7. Do not add new facts, sources, market levels, or forecasts.
8. Do not remove disclaimers.
9. Translate into institutional, concise English that reads naturally (not
   word-by-word).

The English Markdown must keep the same heading hierarchy and Markdown tables,
preserve all calculation formulas, use `YYYY-MM-DD` dates and consistent asset
symbols (Brent, WTI, SPX, KOSPI, TAIEX, DXY, JKM LNG, U.S. 10Y), and start with:

```
# V3 Parallel Appendix: Decision, Evidence, Forecast, and Market Discipline

- Target date: {TARGET_DATE}
- Input report range: {DATE_RANGE}
- Output language: English
- Version: V3-EN
- Note: This appendix is for research use only and does not constitute investment advice. Source claims from the input reports are not independently verified unless explicitly marked.
```

Then render `{OUTPUT_BASENAME_EN}.pdf` from the English Markdown using the same
PDF recipe and render-check.

================================================================
PDF 渲染配方 / PDF RENDERING RECIPE (Markdown → A4 PDF, CJK-safe)
================================================================

Render each PDF **from its Markdown file**, not from chat output. Requirements:
A4 page; Simplified-Chinese-capable font (no garbled text, black boxes, missing
glyphs, overlap, or clipping); body ~9.5–11pt; table ~7.5–9pt; margins ~16–22mm;
tables wrap and must not overflow horizontally; page numbers in the footer.

This environment has `pandoc` and Google Chrome. Use the HTML→Chrome path (it
handles wide CJK tables far better than LaTeX):

```bash
# 1. Markdown -> standalone HTML with CJK-safe, A4 print CSS.
cat > /tmp/_v3_pdf.css <<'CSS'
@page { size: A4; margin: 18mm 16mm; }
html { -webkit-print-color-adjust: exact; }
body { font-family: "PingFang SC","Noto Sans CJK SC","Heiti SC","STHeiti","Songti SC","SimSun",-apple-system,"Helvetica Neue",Arial,sans-serif; font-size: 10.5pt; line-height: 1.5; color:#111; }
h1 { font-size: 17pt; } h2 { font-size: 13pt; border-bottom:1px solid #ccc; padding-bottom:2px; } h3 { font-size: 11.5pt; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; font-size: 8pt; margin: 8px 0; }
th,td { border: 1px solid #999; padding: 3px 5px; word-break: break-word; overflow-wrap:anywhere; vertical-align: top; }
th { background:#f0f0f0; }
code,pre { font-family: ui-monospace,Menlo,monospace; font-size: 8.5pt; }
CSS

pandoc "{OUTPUT_BASENAME}.md" -f gfm -t html5 -s \
  --metadata title="V3 Appendix" \
  -c /tmp/_v3_pdf.css --embed-resources \
  -o "/tmp/{OUTPUT_BASENAME}.html"

# 2. HTML -> PDF via headless Chrome (uses system CJK fonts automatically).
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CHROME" --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="{OUTPUT_BASENAME}.pdf" \
  --print-to-pdf-no-header "file:///tmp/{OUTPUT_BASENAME}.html"
```

Notes:
- If `--no-pdf-header-footer` is rejected by the installed Chrome, retry without
  it (older/newer flags differ); the PDF is still acceptable.
- If a table still overflows, reduce the table `font-size` in the CSS (down to
  7pt), widen margins to 16mm, or split the widest table into two, then
  re-render. Do not sacrifice readability.

### Render-check (required)

After each PDF is produced, verify it visually. Use whichever is available:

```bash
# Rasterise the first / a long-table / the last page to PNGs, then Read them.
pdftoppm -png -r 110 "{OUTPUT_BASENAME}.pdf" /tmp/{OUTPUT_BASENAME}_chk   # poppler
# fallback if pdftoppm is missing:
sips -s format png "{OUTPUT_BASENAME}.pdf" --out /tmp/{OUTPUT_BASENAME}_chk.png
```

Read the rendered image(s): confirm the first page, at least one long-table
page, and the last page show **no** garbled CJK, black boxes, overlap, or
clipped tables. If a problem is found, adjust the CSS / margins / table width
per the notes above and regenerate before continuing.

================================================================
最终交付 / FINAL DELIVERY
================================================================

When all four files exist and both PDFs pass the render-check, stop. The four
files in the run folder are the deliverable:

- `{OUTPUT_BASENAME_CN}.md`
- `{OUTPUT_BASENAME_CN}.pdf`
- `{OUTPUT_BASENAME_EN}.md`
- `{OUTPUT_BASENAME_EN}.pdf`

In your final chat message give only a one-line confirmation that the Chinese
appendix was generated and the English was translated from it and both PDFs were
rendered from their Markdown. Do not paste the appendix body into chat.
