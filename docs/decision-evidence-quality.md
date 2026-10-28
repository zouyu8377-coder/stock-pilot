# 决策输出质量修正

## 根因

2026-09-08 的失败请求消耗12000个输出token，其中11723为推理，仅277用于正文。
同时，沪电股份的旧毛利率反证来自2025年半年报及摘要。原先首页只显示反证计数的固定提示，没有日期、问题、原因和出处；摘要与全文还被重复累计。

## 调整

- 本地日常分析配置 `AGENT_REVIEW_THINKING=disabled`，保留12000输出上限、既有引用和账户约束校验。可显式配置enabled恢复思考，不自动提高预算。
- 资料抓取优先新公告，不让旧公告的关键词命中覆盖新报告。
- 当前证据窗口暂定180天，是产品风控策略而非投资有效期定律。历史或无日期资料保留备查，不单独触发当前仓位硬约束；并不意味着旧风险已消失。
- 同日同问题同结论的报告摘要和全文合并为一项，原始items不删除。
- 模型输入补入原先遗漏的大盘广度、持仓盘中量价、海外产业链和外部驱动资料，原文核验结论附来源、日期和时效标签。
- 建议需有当前仓位立场、最多三条事实论证、调整条件和反向情景。资料不支持的海外市场判断不能编造；无持仓的候选方向不强制要求现有仓位立场。
- 首页突出当前建议及调整条件，论证与原文折叠备查。规则告警不能占满建议展示名额。

## 边界

这些变更改善证据传递和建议可解释性，不等于已覆盖全球新闻，也不能保证模型建议有效。
可执行建议仍由用户确认，系统不自动交易。历史背景与当前风险需持续用新资料复核。
# Manual Analysis And Decision Facets

- Manual workflow, review, follow-up, morning-check button and confidence-refresh calls are exempt from daily model quotas. Their requests and tokens remain recorded, without consuming automatic quotas.
- Scheduled close and morning runs retain quotas and automatic retry backoff. Nested calls inherit the root trigger; an automatic follow-up cannot bypass the quota by calling a manual-labelled function.
- Each manual workflow remains bounded to one initial analysis plus at most one follow-up after collecting new evidence. Each generation allows one format correction; concurrency, cancellation and timeout protections remain active. Provider-side limits are unchanged.
- New model results include `technical_analysis`, `news_analysis` and `confidence_reason`. Technical and news summaries must cite the existing evidence catalog via the item's evidence references, explain source dates and disclose missing data. Confidence is an evidence-based qualitative judgment, not a calibrated probability of profit.
- The cockpit shows the current stance and confidence explanation, with technical/news analysis, reasoning and counter-scenario expandable. Old reports stay readable and are explicitly marked as lacking these new fields; they are not retrospectively fabricated.
