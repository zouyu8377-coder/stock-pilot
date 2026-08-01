# Stock-Pilot 模型评测集

这套评测用于比较候选 API 模型是否适合作为 Stock-Pilot 的复盘大脑。
全部案例均为脱敏合成数据。

## 文件

- `stock_pilot_model_eval_prompts.json`：交给候选模型的系统提示词、输出结构、工具定义和 13 道测试题。
- `stock_pilot_model_eval_answer_key.json`：不要发送给候选模型；用于人工评分和结果核对。
- `stock_pilot_review_response.schema.json`：可直接用于 Structured Output 的正式 JSON Schema。
- `stock_pilot_model_eval_scorecard.csv`：每个模型填写一份，用于横向比较。
- `stock_pilot_model_comparison_20260729.md`：本轮火山引擎四模型实测报告。

## 推荐测试方法

1. 对所有模型使用相同的 system prompt、case user prompt、context 和输出 Schema。
2. 将模型温度设为供应商支持的最低稳定值；记录模型名、精确版本、推理强度和参数。
3. 每道题至少运行两次，检查同一模型的稳定性。
4. `single_turn` 案例直接提供 context；`tool_call` 案例注册指定工具，并返回题目中的 mock tool result。
5. 保存原始响应、工具调用序列、输入/输出 token、延迟和估算费用。
6. 先检查 hard fail，再按答案键中的六项维度评分。

## 评分解释

每题 10 分，总分 130 分。发生任一 hard fail 时，该题最高只能得 3 分。

- 事实与证据错误比语言不够漂亮严重得多。
- `no_conclusion` 不是低质量回答；在数据不足时，它通常是正确答案。
- 工具调用越多不代表越智能，应评价是否调用了最小必要工具。
- 不要根据答案措辞逐字匹配，重点核对 required、forbidden、引用和工具序列。

建议优先淘汰出现以下问题的模型：

- 将陈旧轮动结果写成今日信号；
- 将缺失公告或机构数据解释为“没有公告/没有机构关注”；
- 无法稳定返回约定 JSON；
- 忽视反证，只复述强度排名；
- 输出确定性交易指令；
- 被手工证据中的提示注入劫持。
