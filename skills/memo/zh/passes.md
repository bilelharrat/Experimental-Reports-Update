---
en_sha256: f780b4d636152f6be1aa00f72a16fbe4213adabef68593c0611fadfa5629001a
---
---
kind: memo_phase2_passes
---
# 第二阶段分析 pass（调研环节）

每个 pass 一个块，按派发顺序排列（此处的顺序即流水线启动它们的顺序
—— 为钉定事实供料的 pass 须排在最前）。每个块包括：`## pass: <id>`、
一个含 `label`（UI 线程名称）和 `artifact`（该 pass 写出的
analysis/<file>.md）的 yaml 围栏，然后是该 pass 的调研重点散文（加载时
会规范化空白字符）。公司类型的补充内容在运行时来自
skills/memo/types/<type>.md 的 `research_focus`。

从代码中沿袭的说明：派发顺序即执行顺序：进程池立即运行前 max-workers
个规格，其余排队，因此末尾两个 pass 总是最后完成。
MEMO_SPINE_PIN_FEEDING_PASSES 中的每个 pass 都须保持在立即执行窗口内
（推测性主干会等待它们再启动），并将最偏向单一章节的补色 pass 放入
队列 —— 它们的迟到正是增量检查（delta check）的用途所在，增量检查将其
视为增量内容。

## pass: arithmetic_denominators
```yaml
label: Arithmetic / pressure tests
artifact: pressure_tests.md
```
对估值、合同金额、SAFE/SPV 经济结构、收入确认、ARR/收入替代指标、
单位算术，以及已披露数字的隐含意义进行压力测试。给出区间，而不是
虚假的精确。

## pass: time_base
```yaml
label: Time-base integrity
artifact: time_base_checks.md
```
为每一项估值、轮次、合同、管线、ARR/收入、融资和客户指标标注日期。
区分同期数据、过时标记、前瞻性和滞后性的说法。

## pass: growth_bridge
```yaml
label: Growth bridge
artifact: growth_bridge.md
```
将已披露的商业活动桥接到建模的收入或价值：具约束力的合同、可取消的
合同、谅解备忘录（MOU）、意向书（LOI）、管线、转化率区间、实施能力，
以及确认时点。

## pass: valuation_comps
```yaml
label: Valuation comparables
artifact: valuation_comps.md
```
构建带增长调整倍数的可比公司集合，收集先例交易，判断三种方法（可比
公司 / 先例交易 / DCF-盈利能力）中哪一种可以基于现有披露运行、其余
为何不能，并推导出隐含的合理估值区间，展示算术过程。把入场价格换算成
它已经为多少增长和利润率买了单。

## pass: exit_paths
```yaml
label: Exit paths
artifact: exit_paths.md
```
梳理现实可行的退出路径：IPO 准备度和时机的证据、并购（具名的潜在
收购方及各自面临的战略或反垄断约束）、该标的在二级市场的深度、未来
12-36 个月内带日期的催化剂，以及情景表所需的退出年份/倍数框架（熊市/
基准/牛市情形的退出估值及稀释假设）。

## pass: replacement_coexistence
```yaml
label: Replacement vs coexistence
artifact: replacement_vs_coexistence.md
```
判断公司是替代在位者、作为附加层与之共存、通过在位者进行授权，还是
依赖标准和生态系统的采用。

## pass: competitive_rights
```yaml
label: Competitive compression
artifact: competitive_notes.md
```
评估竞争压缩、IP/专利的持久性、权利或标准方面的杠杆、可防御性、替代
技术路线，以及可能削弱定价权的因素。

## pass: alternative_explanations
```yaml
label: Alternative explanations
artifact: disconfirming_evidence.md
```
提出对事实最有力的非看多解读。识别反面证据、下行敏感性，以及会改变
决策的具体风险或估值敏感因素。

## pass: market_sizing
```yaml
label: Market sizing / TAM
artifact: market_sizing.md
```
测算公司实际参与竞争的市场规模。首先收集能找到的每一个外部估计 ——
只要存在，至少三个：行业研究机构（Gartner、IDC、Stratpace、Technavio、
MarketsandMarkets、Grand View、Statista ……）、公司自己宣称的 TAM、
银行或分析师的测算 —— 并为每一个记录：出自谁、统计口径（定义）、
数值、年份、检索日期和 URL。绝不因某个估计与公司收入或另一估计相悖
而将其视为不可用并丢弃；保留它并解释口径差异（一个基础模型支出数字、
一个软件替代数字和一个劳动力替代数字衡量的是不同的东西，可以同时
成立）。然后构建本备忘录自己的推导，点明每一个输入（基数、增长率、
替代或渗透系数，以及各自的来源），并与外部估计进行对账，说明本备忘录
采用哪个口径及原因。然后是 TAM/SAM/SOM 及各自的推导方法、市场定义与
价值链位置、增长驱动因素（每个驱动因素附一个支撑数据点）、约束或补贴
该业务的政策/监管环境，以及天花板所在（$20B / $100B / $500B 的企业
价值区间）。标记每一个公司自报的数字与独立测算的区别。

## pass: team_governance
```yaml
label: Team & governance
artifact: team_governance.md
```
评估领导层的过往业绩、关键人物依赖、董事会构成与独立性、所有权与投票
控制权、员工持股计划（ESOP）、保护性条款、缺位的高管（尤其是 CFO）、
审计历史、关联方敞口，以及上市公司化的准备度。陈述事实并注明日期；
将经核实的履历与公司自称的简介区分开。

## pass: deployment_behavior
```yaml
label: Adoption ladder
artifact: adoption_ladder.md
```
按产品/用例评估部署深度和采用成熟度。区分已宣布、试点、具名生产环境、
可复制的生产环境、续约/增购，以及大规模部署的证据。

## pass: gtm_operating_burden
```yaml
label: Distribution / GTM
artifact: distribution_notes.md
```
评估分销模式、获客路径、销售周期、实施负担、预算归属方、渠道杠杆、
运营商或企业级准入，以及 GTM 压力。
