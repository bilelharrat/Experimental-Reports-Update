# 报告生成提示词（中文版）

这个文件夹是 `skills/memo/` 下英文提示词的中文对照版，路径一一对应。
**报告代理实际读取的是英文版**；中文版是给前辈和团队阅读、修改用的。

```
zh/
  voice_contract.md        报告的语气与写法（面向 LP 的联合投资口吻、结论先行）
  structure_addendum.md    v2 结构的通用规则：数据诚实、引用标注、图表、
                           解释性文风、"教学式而非断言式"
  risk_card_v2.md          完整版报告的八行风险卡片
  risk_card_compact.md     精简版报告的风险要点格式
  passes.md                第二阶段的 12 个调研 pass：编号、名称、产出文件、调研重点
  structures/              各阶段的报告结构：late_v2（完整版）、late_compact（精简版）、
                           growth（成长期）、early（早期）；每个 `## section:`
                           块下面的正文就是该章节的写作要求，yaml 围栏是技术字段
  types/                   公司类型视角：AI 大模型、AI 基础设施、AI 应用、
                           AI 视频与短剧、机器人、其他 —— 头部 yaml 里可选地
                           定义评分权重和各 pass 的调研重点，正文是第三阶段的分析视角
```

## 修改流程

1. 直接修改中文版的正文。**yaml 围栏（```yaml … ```）里的内容是技术字段，
   请勿改动**；`## section:` / `## pass:` 这类标题行也请保持不变。
2. 改完后告诉 Ben "sync zh → en"，由 Claude 把改动同步到英文版（代理只读英文），
   并重新盖章（每个中文文件头部的 `en_sha256` 记录它对应的英文版本）。
3. 如果英文版被改动而中文版没有同步，测试会失败提醒。

## 术语对照（固定译法）

| 英文 | 中文 |
| --- | --- |
| investment highlights | 核心投资亮点 |
| key risks | 核心风险提示 |
| verdict / recommendation | 结论 / 投资建议 |
| moat | 护城河 |
| valuation / fair value range | 估值 / 合理估值区间 |
| bear / base / bull case | 熊市 / 基准 / 牛市情形 |
| MOIC / IRR | 回报倍数 / 内部收益率 |
| unit economics | 单位经济 |
| run-rate | 年化收入（最近一期 ×12） |
| pinned (fact sheet) | 已钉定（共享事实表） |
| Impact（风险卡片行） | 影响有多大 |
| Verdict（风险卡片行） | 一句话结论 |
