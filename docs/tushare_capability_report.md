# Stock-Pilot 数据能力与 Tushare 权限核查报告

## 1. 执行摘要

本次核查只做只读探测，未修改现有 FastAPI、前端、数据库结构、行情、缓存或 LLM 分析逻辑。新增文件仅限独立探测脚本与报告文件。

当前 Token 立即可支持的高价值自动化模块：

1. **龙虎榜事件卡**：`top_list` 与 `top_inst` 均返回有效数据，可生成汇总 + 席位级事件卡，能识别机构专用、深股通/沪股通专用等席位文本。
2. **ETF 资金流观察**：`etf_share_size`、`fund_nav`、`fund_daily`、`fund_share` 可用，能够覆盖 159382.SZ 创业板人工智能ETF南方和 159934.SZ 黄金ETF易方达的份额、规模、净值、收盘价与份额变化。
3. **两融风险观察**：`margin_detail` 对样例标的可用，但频率较低，适合离线/低频缓存后生成 5日/20日融资余额变化与风险提示。
4. **资金流辅助信号**：`moneyflow_ths` 与 `moneyflow` 可用，字段能覆盖主力/大单/中单/小单口径，但应作为低权重辅助证据，不能等同真实机构买卖。
5. **公告与调研事实层**：`anns_d`、`stk_surv` 可用，可做公告索引、调研索引、事实事件入口；调研全文仍需结合公告 URL/PDF 另行抽取。
6. **事件风险层的一部分**：`stk_holdertrade`、`block_trade` 可用，`repurchase`、`pledge_detail`、`pledge_stat` 可达但样例无数据，适合低频扫描；`share_float` 权限不足。
7. **行业与宏观的一部分**：同花顺行业指数列表和行情 `ths_index`、`ths_daily` 可用，商品期货 `fut_daily` 与外汇 `fx_daily` 可用；Tushare `index_daily`、`daily` 当前权限不足，但项目已有本地日K可替代个股日线。

当前不能立即自动化开发或需延后：

- **股东户数/筹码集中度**：`stk_holdernumber` 对全部测试股票均明确权限不足，暂不能自动接入。
- **限售股解禁**：`share_float` 权限不足，不能作为第一版自动风险卡核心来源。
- **Tushare 分钟线替代 AKShare**：`stk_mins` 权限不足，其他尝试的分钟线名称无效；当前阶段继续保留 AKShare。
- **交易日历**：`trade_cal` 权限不足；可先用本地数据最新日期或简单交易日规则兜底。
- **盘中 ETF IOPV/申赎参考**：本次未找到可直接调用的稳定 Tushare 接口；测试的 `etf_cash`、`etf_substitute` 接口名无效，应暂缓或改用其他实时行情源。

第一阶段建议开发范围不超过四个模块：

1. 龙虎榜事件卡；
2. ETF 份额/规模/NAV 资金流卡；
3. 两融 + 资金流低权重风险/热度卡；
4. 公告/调研/增减持/大宗交易事实时间线，并导出 Analysis Packet。

必须继续手动维护的数据：真实账户持仓、成本、仓位、交易计划、手动截图证据、未接入的股东户数、解禁数据、盘中 IOPV、宏观利率/美债收益率等高质量外部宏观变量。

## 2. 核查环境

- 核查日期时间：2026-05-24 19:54:41
- Python 版本：3.12.9
- tushare 版本：1.4.29
- Token 是否成功读取：Yes
- Token 来源类型：现有代码中读取到；报告与 JSON 均未显示 Token 值
- 使用的数据日期范围：主要为最近约 90 天至 400 天；接口返回最新样例多为 2026-05-21 / 2026-05-22
- 最近交易日锚点：`trade_cal` 权限不足，脚本回退到 2026-05-21；部分接口实际返回 2026-05-22 数据
- 样例股票：601899.SH、603993.SH、002463.SZ、002916.SZ、000657.SZ
- 样例 ETF：159382.SZ、159934.SZ
- 是否修改业务代码：No
- 新增非业务文件：`scripts/tushare_capability_probe.py`、`docs/tushare_capability_report.json`、`docs/tushare_capability_report.md`

安全备注：当前项目中已有 Tushare Token 硬编码实现，核查脚本只读取既有配置，不输出 Token。建议后续 P0 安全任务将其迁移到 `.env` / 环境变量，并避免异常日志打印敏感配置。

## 3. 接口权限矩阵

| 数据主题 | 候选接口 | 状态 | 是否返回有效数据 | 样例标的 | 核心字段满足度 | 权限/错误摘要 | 推荐优先级 | 推荐用途 |
|---|---|---:|---:|---|---|---|---|---|
| 交易日历 | trade_cal | PERMISSION_DENIED | No | SSE | 不满足 | 明确无访问权限 | P2 | 日期锚点可由本地数据兜底 |
| 股东户数 | stk_holdernumber | PERMISSION_DENIED | No | 601899/002463/002916/000657 | 不满足 | 明确无访问权限 | 暂缓 | 手动补录/截图证据 |
| 龙虎榜汇总 | top_list | AVAILABLE_WITH_DATA | Yes，74 行 | 最近交易日 | 满足 | 可返回买入/卖出/净额/原因 | P0 | 龙虎榜事件卡 |
| 龙虎榜席位 | top_inst | AVAILABLE_WITH_DATA | Yes，798 行 | 最近交易日 | 满足 | 可返回营业部、机构、深股通等席位文本 | P0/P1 | 席位结构卡 |
| 基金映射 | fund_basic | AVAILABLE_WITH_DATA | Yes，2624 行 | ETF 市场 | 基本满足 | 可做基金基础映射 | P0 | ETF 代码确认 |
| ETF 基础信息 | etf_basic | AVAILABLE_WITH_DATA | Yes | 159382.SZ | 满足 | 返回基金简称、全称、跟踪指数、管理人 | P1 | ETF 画像 |
| ETF 份额 | fund_share | AVAILABLE_WITH_DATA / REQUEST_FAILED | 159382 有数据；159934 因 1次/分钟限频失败 | 159382/159934 | 满足份额，不含规模 | 对第二次调用触发限频 | P1 | 份额变化低频缓存 |
| ETF 份额规模 | etf_share_size | AVAILABLE_WITH_DATA | Yes，两个 ETF 均 75 行 | 159382/159934 | 满足 | 返回 total_share/total_size | P0 | ETF 资金流第一版核心接口 |
| ETF NAV | fund_nav | AVAILABLE_WITH_DATA | Yes，76 行 | 159382.SZ | 满足 | 返回 unit_nav/adj_nav 等 | P1 | ETF 折溢价/净值辅助 |
| ETF 行情 | fund_daily | AVAILABLE_WITH_DATA | Yes，75 行 | 159382.SZ | 满足 | 返回 OHLC/成交量/成交额 | P1 | ETF 收盘价与涨跌幅 |
| ETF 扩展指数信息 | etf_index | AVAILABLE_NO_DATA | No | 159382.SZ | 部分满足 | 接口可达但样例无数据 | P2 | 暂缓 |
| ETF 申赎/IOPV 候选 | etf_cash / etf_substitute | INVALID_ENDPOINT_OR_DEPRECATED | No | 159382.SZ | 不满足 | 接口名无效 | 暂缓 | 需另找来源 |
| 融资融券 | margin_detail | AVAILABLE_WITH_DATA / REQUEST_FAILED | 沪电有数据；后续标的触发限频 | 002463/002916/601899 | 满足 | 低频限制明显 | P1 | 杠杆拥挤度风险卡 |
| 同花顺资金流 | moneyflow_ths | AVAILABLE_WITH_DATA | Yes，三个标的均 75 行 | 601899/002463/002916 | 满足 | 返回主力/5日/大中小单字段 | P1/P2 | 低权重辅助信号 |
| Tushare 资金流 | moneyflow | AVAILABLE_WITH_DATA / REQUEST_FAILED | 紫金有数据；后续触发限频 | 601899/002463/002916 | 满足 | 低频限制明显 | P2 | 辅助信号/校验 |
| 重要股东增减持 | stk_holdertrade | AVAILABLE_WITH_DATA | Yes，沪电 2 行 | 002463/601899 | 满足 | 可返回股东、增减持方向、数量、比例 | P1 | 风险事件卡 |
| 公司回购 | repurchase | AVAILABLE_NO_DATA | No | 002463/601899 | 字段满足 | 样例期无数据 | P1 | 事件扫描 |
| 限售解禁 | share_float | PERMISSION_DENIED | No | 002463/601899 | 不满足 | 明确无访问权限 | 暂缓 | 手动维护或另找来源 |
| 大宗交易 | block_trade | AVAILABLE_WITH_DATA | Yes，沪电 6 行 | 002463/601899 | 满足 | 返回价格、量额、买卖席位 | P2 | 事件证据 |
| 质押明细 | pledge_detail | AVAILABLE_NO_DATA | No | 002463/601899 | 字段满足 | 样例期无数据 | P2 | 低频风险扫描 |
| 质押统计 | pledge_stat | AVAILABLE_NO_DATA | No | 002463/601899 | 字段满足 | 样例期无数据 | P2 | 低频风险扫描 |
| 公告索引 | anns_d | AVAILABLE_WITH_DATA | Yes，沪电 109 行 | 002463/000657 | 基本满足 | 有标题、日期、URL；无结构化分类 | P1 | 事实时间线 |
| 机构调研 | stk_surv | AVAILABLE_WITH_DATA | Yes，沪电 146 行 | 002463/000657 | 索引满足，全文不足 | 有调研日期/机构/接待方式/人员 | P1 | 调研索引卡 |
| 沪深300指数日线 | index_daily | PERMISSION_DENIED | No | 000300.SH | 不满足 | 明确无访问权限 | 暂缓 | 可改用本地/其他源 |
| 同花顺指数列表 | ths_index | AVAILABLE_WITH_DATA | Yes，409 行 | A股指数 | 满足 | 可获取行业/概念指数清单 | P1/P2 | 板块相对强弱 |
| 同花顺指数行情 | ths_daily | AVAILABLE_WITH_DATA | Yes，75 行 | 885800.TI | 满足 | 返回行业指数 OHLC/成交/换手 | P1/P2 | 板块强弱 |
| 个股 Tushare 日线 | daily | PERMISSION_DENIED | No | 601899.SH | 不满足 | 明确无访问权限 | 暂缓 | 本地 parquet 已替代 |
| 商品期货 | fut_daily | AVAILABLE_WITH_DATA | Yes，CU.SHF 75 行 | 铜期货 | 基本满足 | 可返回价格、成交、持仓 | P2 | 金属宏观变量 |
| 外汇 | fx_daily | AVAILABLE_WITH_DATA | Yes，USDCNH 101 行 | USDCNH.FXCM | 基本满足 | 可返回 bid/ask OHLC | P2 | 汇率变量 |
| 分钟线 | stk_mins | PERMISSION_DENIED | No | 002463.SZ | 不满足 | 明确无访问权限 | 暂缓 | 继续用 AKShare |
| 分钟线候选 | stk_mins_weekly/monthly | INVALID_ENDPOINT_OR_DEPRECATED | No | 002463.SZ | 不满足 | 接口名无效 | 暂缓 | 不采用 |

## 4. 关键接口详细结果

### 4.1 股东户数 / 筹码结构

实际调用：`stk_holdernumber` 对 601899.SH、002463.SZ、002916.SZ、000657.SZ 各测试一次。

结果：全部为 `PERMISSION_DENIED`。

目标字段：`ts_code`、`ann_date`、`end_date`、`holder_num` 本应满足股东户数观察，但当前 Token 无法访问，因此无法自动计算：

- 最近一期股东户数环比变化；
- 最近三期趋势；
- 同期股价涨跌对照；
- 数据滞后天数。

覆盖日期：不可得。

刷新节奏判断：从业务语义看通常随定期报告、临时披露或上市公司公告更新，不是稳定日频数据；但当前无法用 Token 验证实际覆盖。

结论：**不建议第一批自动化开发**。应保留手动补录入口或截图/公告证据入口作为兜底。若未来权限开通，股东户数非常适合进入单票证据页和 Analysis Packet。

### 4.2 龙虎榜汇总与席位明细

实际调用：

- `top_list`：按最近交易日锚点调用，返回 74 行。
- `top_inst`：按最近交易日锚点调用，返回 798 行。

返回字段：

- `top_list`：`trade_date`、`ts_code`、`name`、`close`、`pct_change`、`turnover_rate`、`amount`、`l_sell`、`l_buy`、`l_amount`、`net_amount`、`net_rate`、`amount_rate`、`float_values`、`reason`。
- `top_inst`：`trade_date`、`ts_code`、`exalter`、`buy`、`buy_rate`、`sell`、`sell_rate`、`net_buy`、`side`、`reason`。

能力判断：

- 可取得龙虎榜汇总：Yes。
- 可取得席位级明细：Yes。
- 席位级明细权限不足：No，本次实际可用。
- 可自动生成“龙虎榜事件卡”：Yes。

适合展示：

- 当日总买入、总卖出、净买入；
- 上榜原因；
- 机构专用席位买卖；
- 深股通/沪股通专用席位买卖；
- 营业部席位买卖排名；
- 买卖集中度和净买入占成交额比例。

证据等级：**事实型交易事件**。它可以说明某日上榜原因和席位买卖结构，但不能推断长期持仓意图，也不能把“机构专用买入”直接解释为长期机构建仓。

建议：**第一版立即开发 P0**。

### 4.3 ETF 份额、规模、申赎与 IOPV

映射结果：

- 159382.SZ：`etf_basic` 返回“创业板人工智能ETF南方 / 南方创业板人工智能ETF”，跟踪“创业板人工智能指数”，交易所 SZ。
- 159934.SZ：`etf_share_size` 返回“黄金ETF易方达”，交易所 SZSE。

实际调用结果：

- `fund_share`：159382.SZ 返回 75 行，字段包含 `ts_code`、`trade_date`、`fd_share`、`fund_type`、`market`；159934.SZ 第二次调用触发 1次/分钟限频，不能判为无权限。
- `etf_share_size`：159382.SZ 和 159934.SZ 均返回 75 行，字段包含 `trade_date`、`ts_code`、`etf_name`、`total_share`、`total_size`、`exchange`。
- `fund_nav`：159382.SZ 返回 76 行，包含 `unit_nav`、`accum_nav`、`adj_nav` 等。
- `fund_daily`：159382.SZ 返回 75 行，包含 ETF 日线 OHLC、成交量、成交额。
- `etf_basic`：159382.SZ 返回基础信息。
- `etf_index`：可达但样例无数据。
- `etf_cash`、`etf_substitute`：接口名无效，归类为 `INVALID_ENDPOINT_OR_DEPRECATED`。

能否取得字段：

- 每日份额：Yes，`fund_share.fd_share` 或 `etf_share_size.total_share`。
- 每日规模：Yes，`etf_share_size.total_size`。
- NAV：Yes，`fund_nav.unit_nav/adj_nav`。
- 收盘价：Yes，`fund_daily.close`。
- 份额变化率：Yes，基于 `total_share` 或 `fd_share` 计算。
- 连续净申购/净赎回天数：Yes，基于份额环比方向计算。
- IOPV：No，本次未找到稳定可用接口。
- 盘中申购/赎回参考：No，本次未找到稳定可用接口。

结论：

- `fund_share` 是否可用：可用，但低频限制明显。
- `etf_share_size` 是否可用：可用，并且更适合作为第一版 ETF 资金流核心接口。
- 是否存在字段更完整但权限更高的接口：可能存在更完整的 ETF 申赎清单、PCF、IOPV 或实时接口，但本次测试的相关候选名称无效，不能作为当前可用能力。
- 是否能覆盖 AI ETF 与黄金 ETF：Yes，`etf_share_size` 已覆盖两者。
- 盘中 IOPV/申赎是否可用于 AI ETF：当前不能确认可用；第一版不建议依赖。
- 第一版最低成本方案：`etf_share_size + fund_nav + fund_daily`。

建议：**ETF 资金流模块第一版 P0**，但先做日频，不做盘中 IOPV。

### 4.4 融资融券

实际调用：`margin_detail`。

结果：

- 002463.SZ 返回 74 行，有效字段包括 `trade_date`、`ts_code`、`rzye`、`rqye`、`rzmre`、`rqyl`、`rzche`、`rqchl`、`rqmcl`、`rzrqye`。
- 002916.SZ、601899.SH 后续调用触发 1次/分钟限频，不能判定无权限。

字段说明：

- `rzye`：融资余额；
- `rqye`：融券余额；
- `rzmre`：融资买入额；
- `rzche`：融资偿还额；
- `rzrqye`：融资融券余额。

能力判断：

- 是否可用：Yes，但需要低频缓存与节流。
- 是否值得纳入第一版风险事件卡：Yes，建议 P1。
- 推荐派生字段：
  - 近 5 日融资余额变化率；
  - 近 20 日融资余额变化率；
  - 融资余额 / 流通市值；
  - 股价上涨但融资余额快速扩张提示；
  - 融资余额扩张但股价滞涨/回落提示。

注意：频率限制较低，不能在用户每次打开页面时实时批量拉取；建议后台每日更新或按标的缓存。

### 4.5 同花顺口径或其他供应商口径资金流

实际调用：

- `moneyflow_ths`：601899.SH、002463.SZ、002916.SZ 均返回 75 行。
- `moneyflow`：601899.SH 返回 75 行，后续标的触发 1次/分钟限频。

返回字段：

- `moneyflow_ths`：`trade_date`、`ts_code`、`name`、`pct_change`、`latest`、`net_amount`、`net_d5_amount`、`buy_lg_amount`、`buy_lg_amount_rate`、`buy_md_amount`、`buy_md_amount_rate`、`buy_sm_amount`、`buy_sm_amount_rate`。
- `moneyflow`：小单、中单、大单、特大单买卖量额，以及 `net_mf_vol`、`net_mf_amount`。

结论：

- 哪个接口可用：`moneyflow_ths` 和 `moneyflow` 均可用，前者更接近同花顺界面的“主力/大单/中单/小单”口径。
- 是否与同花顺界面口径接近：字段语义接近，但未与截图逐项核对，不能保证数值完全一致。
- 是否值得第一版接入：建议 P1/P2，作为辅助信号，不作为核心买卖触发器。
- 若权限成本较高是否应先手动截图：当前可用，但频率限制存在；若后续批量使用受限，可保留手动截图补录作为兜底。

重要约束：资金流是行情供应商对成交单的拆分口径，**不等于真实机构买卖，不可单独作为买卖触发器**。建议在 LLM Prompt 中明确降权，例如“低权重辅助证据”。

### 4.6 增减持 / 回购 / 解禁 / 大宗 / 质押

#### stk_holdertrade：重要股东增减持

- 状态：`AVAILABLE_WITH_DATA`
- 样例：002463.SZ 返回 2 行。
- 字段：`ts_code`、`ann_date`、`holder_name`、`holder_type`、`in_de`、`change_vol`、`change_ratio`、`after_share`、`after_ratio`、`avg_price`、`total_share`。
- 能否生成风险事件提醒：Yes。
- 推荐优先级：P1。
- 展示位置：风险事件卡、单票证据页、组合驾驶舱预警、Analysis Packet。

#### repurchase：公司回购

- 状态：`AVAILABLE_NO_DATA`
- 样例期未返回数据，但字段可用：`ts_code`、`ann_date`、`end_date`、`proc`、`exp_date`、`vol`、`amount`、`high_limit`、`low_limit`。
- 能否生成事件提醒：Yes，但需要扫描更多标的/更长时间。
- 推荐优先级：P1。
- 展示位置：风险事件卡、单票证据页、Analysis Packet。

#### share_float：限售股解禁

- 状态：`PERMISSION_DENIED`
- 当前不可自动取得。
- 推荐优先级：暂缓。
- 展示位置：仍应进入风险事件卡，但第一版需手动维护或使用其他来源。

#### block_trade：大宗交易

- 状态：`AVAILABLE_WITH_DATA`
- 样例：002463.SZ 返回 6 行。
- 字段：`ts_code`、`trade_date`、`price`、`vol`、`amount`、`buyer`、`seller`。
- 能否生成风险事件提醒：Yes，但解释需谨慎，只能作为成交事实。
- 推荐优先级：P2。
- 展示位置：单票证据页、Analysis Packet。

#### pledge_detail / pledge_stat：质押明细与统计

- 状态：`AVAILABLE_NO_DATA`
- 字段结构可用，样例期无数据。
- 能否生成风险事件提醒：Yes，但需要更长周期低频扫描。
- 推荐优先级：P2。
- 展示位置：风险事件卡、组合驾驶舱预警、Analysis Packet。

应用到当前关注场景：

- PCB 强势股高位：可自动观察增减持、两融过热、大宗交易；解禁暂不可自动化。
- 紫金/洛钼等待修复：可自动观察大宗、质押、两融、资金流；真实供给压力仍需公告/股东户数/解禁补充。
- 中钨高新观察：解禁权限不足，需手动或其他来源；可通过公告、调研、增减持、大宗做部分风险监控。

### 4.7 公告索引与原文链接

实际调用：`anns_d`。

结果：002463.SZ 最近周期返回 109 行。

字段：`ann_date`、`ts_code`、`name`、`title`、`url`。

能力判断：

- 公告标题：Yes。
- 股票代码：Yes。
- 公告发布日期：Yes。
- 公告类别：No，未返回结构化类别，需要基于标题规则分类。
- PDF 原文链接或可下载地址：返回的是公告详情 URL，不一定是直接 PDF 下载地址；可作为后续抓取入口。

适合第一版做：

- 公告索引时间线；
- 标题关键词分类：定期报告、业绩预告、业绩快报、投资者关系记录、回购、增减持、解禁、异常波动、风险提示、项目投资等；
- Analysis Packet 中引用公告标题、日期和链接。

不建议本次开始做：全文 RAG、PDF 下载解析、公告正文事实抽取。

推荐优先级：P1。

### 4.8 机构调研索引

实际调用：`stk_surv`。

结果：002463.SZ 返回 146 行。

字段：`ts_code`、`name`、`surv_date`、`fund_visitors`、`rece_place`、`rece_mode`、`rece_org`、`org_type`、`comp_rece`。

能力判断：

- 自动取得调研索引：Yes。
- 调研日期：Yes。
- 机构名称：Yes，`rece_org`。
- 接待方式：Yes，`rece_mode`。
- 参与人员：部分有，`comp_rece`；`fund_visitors` 样例为 `--`。
- 是否包含正文：No，本接口更像索引，不包含完整问答正文。

后续是否需要公告 PDF：Yes。若要抽取订单、产能、价格、良率、需求、客户结构等事实，仍需结合公告 URL/PDF 或投资者关系活动记录正文。

前端展示建议：

- “最近调研热度”卡片：近 30/90 天调研次数、机构类型、最近调研日期；
- “调研机构列表”折叠展示；
- 与公告索引联动打开原文。

推荐优先级：P1。

### 4.9 行业、相对强弱与宏观

当前项目已有能力：

- 本地个股日K parquet 足够计算个股 1日、5日、20日收益；
- 技术指标模块已计算 MA5/10/20/30/60、RSI14、MACD；
- stock_meta 已有行业、地区、上市日期，可做粗行业分组。

本次 Tushare 探测：

- `index_daily`：沪深300指数日线权限不足。
- `daily`：个股 Tushare 日线权限不足，但本地 parquet 已覆盖个股日K。
- `ths_index`：可用，返回 409 个同花顺指数/板块列表。
- `ths_daily`：可用，返回同花顺指数日线。
- `fut_daily`：可用，样例 CU.SHF 返回铜期货日线。
- `fx_daily`：可用，样例 USDCNH.FXCM 返回外汇日线。

可低成本实现：

1. 个股相对自身行业或观察篮子的 1日/5日/20日强弱：使用本地日K + 自定义篮子即可。
2. PCB 观察篮子：沪电股份、深南电路、中钨高新、创业板人工智能ETF；股票用本地日K，ETF 用 `fund_daily`。
3. 金属观察篮子：紫金矿业、洛阳钼业、黄金ETF；可加入 `fut_daily` 的沪铜/黄金期货（需确认具体主力合约代码策略）。
4. 同花顺板块指数相对强弱：使用 `ths_index` + `ths_daily`。

仍缺或建议暂缓：

- 沪深300指数日线：Tushare 权限不足，可用其他免费源或本地维护指数 parquet。
- 行业板块上涨家数、成交额占比、龙头一致性：需要成分股映射和全市场日线聚合，第一版可先用观察篮子替代。
- 黄金、铜、原油、美元指数、美债收益率：Tushare 已验证部分商品/汇率可用，但美国利率/美债收益率稳定性未验证，建议后续通过更专业宏观数据源解决。

### 4.10 历史分钟线

当前项目使用：`akshare.stock_zh_a_hist_min_em`。

本次核查：

- `stk_mins`：`PERMISSION_DENIED`。
- `stk_mins_weekly`、`stk_mins_monthly`：`INVALID_ENDPOINT_OR_DEPRECATED`。

判断：

- 当前 Token 无法使用 Tushare 分钟线。
- 支持周期和历史覆盖不可验证。
- 不值得当前阶段重构分钟线。
- 当前阶段建议继续保留 AKShare 作为盘中展示来源。
- 如果未来做分钟级回测，再单独评估更稳定的分钟级数据源与本地落库方案。

## 5. 与现有项目能力的重叠分析

### 5.1 已有数据，无需重复开发

- **实时行情**：`easyquotation` 腾讯源已提供 `price`、`change_pct`、`name`、`volume`、`market_cap`、`float_market_cap`、`pe`、`pb`、`turnover_rate`、`volume_ratio`。
- **本地日K**：`backend/data/base_market` 有 6226 个 parquet 文件。样例标的覆盖：
  - 601899.SH：2008-04-25 至 2026-05-22；
  - 603993.SH：2012-10-09 至 2026-05-22；
  - 002463.SZ：2010-08-18 至 2026-05-22；
  - 002916.SZ：2017-12-13 至 2026-05-22；
  - 000657.SZ：1996-12-05 至 2026-05-22。
- **日K字段**：`date`、`open`、`high`、`low`、`close`、`volume`、`amount`、`turn`、`pctChg`。
- **复权口径**：增量更新使用 BaoStock `adjustflag="3"`，按 BaoStock 语义为不复权口径；报告中建议在 UI/Prompt 中明确“当前为未复权日K”。
- **技术指标**：MA5、MA10、MA20、MA30、MA60、RSI14、MACD，并输出均线序列给 K 线叠加。
- **股票元数据**：`stock_meta.parquet` 5513 行，字段 `ts_code`、`symbol`、`name`、`area`、`industry`、`list_date`。
- **公司画像**：已有本地元数据 + Tushare `stock_company` + 本地概念标签 + 规则推断，字段包括主营业务、核心产品、产业链位置、核心逻辑、概念标签、公司类型、利润驱动、竞争优势、风险点。
- **数据覆盖度**：已能区分“主营业/产品结构”“前高与套牢区分布”等已覆盖项，以及订单产能、北向、机构持仓等缺失项。
- **Prompt Builder**：已注入股票信息、公司画像、交易环境、模型规则、数据覆盖度、技术指标、快速分析结论、行业关键因子、行业模板和数据可信度约束。
- **持久化机制**：已有 parquet、JSON、内存热缓存、深度分析 JSON 缓存、公司画像 JSON 缓存。
- **更新任务**：应用启动时会检查并后台增量更新本地日K，有 lock/status 文件和 BaoStock 更新链路。

### 5.2 已有但前端未充分展示的数据

- easyquotation 的市值、流通市值、PE、PB、换手率、量比；
- 本地日K中的成交额、换手率、涨跌幅；
- 均线序列和部分技术指标；
- 公司画像中的概念标签、核心产品、产业链位置、风险点；
- 数据覆盖度中的“已覆盖/缺失数据”结构；
- 深度分析缓存状态与 Analysis Prompt。

### 5.3 已有但 Prompt 未充分注入的数据

Prompt 已注入主干数据，但以下可增强：

- 实时行情中的市值、流通市值、PE/PB、换手率、量比；
- 近 5/20/60 日涨跌幅、振幅、成交额变化；
- 观察篮子相对强弱；
- 龙虎榜、两融、资金流、公告/调研、增减持等新增事实层。

### 5.4 新数据，可直接复用现有架构

- 低频事实数据：龙虎榜、公告、调研、增减持、回购、大宗、质押；可复用 JSON/parquet 缓存。
- 日频序列数据：ETF 份额/规模、NAV、fund_daily、两融、资金流；可复用 parquet 缓存。
- Analysis Packet：可复用 `build_human_prompt` 与数据覆盖度约束，新增结构化聚合层即可。

### 5.5 需要新增数据表或缓存的内容

- `data/tushare/dragon_tiger/`：龙虎榜汇总与席位明细。
- `data/tushare/etf/`：ETF share/size/nav/daily。
- `data/tushare/margin/`：两融明细。
- `data/tushare/moneyflow/`：资金流日频。
- `data/tushare/events/`：增减持、回购、大宗、质押。
- `data/tushare/announcements/`：公告索引。
- `data/tushare/surveys/`：机构调研索引。

### 5.6 会造成架构大改，建议延后

- 全市场板块广度和成分股映射系统；
- 公告 PDF 全文解析和 RAG；
- 分钟级本地回测数据库；
- 账户级持仓/交易日记自动同步；
- 盘中 IOPV/申赎实时系统；
- 多来源宏观数据库。

## 6. 推荐的数据分层

### A. 自动事实层

内容：日K、实时行情、公司画像、ETF 份额/规模/NAV、龙虎榜、公告索引、调研索引、两融、增减持、回购、大宗、质押。

是否允许 LLM 当作事实引用：**允许**，但必须附带来源、日期、字段名，并避免超出字段本身的推断。

### B. 自动辅助信号层

内容：技术指标、相对强弱、资金流、行业指数强弱、融资变化率、ETF 份额变化率。

是否允许 LLM 当作事实引用：**允许引用数值事实，但不能把信号解释为确定因果**。例如资金流只能说“供应商口径显示净流入”，不能说“机构正在买入”。

### C. 手动账户层

内容：真实持仓、成本、仓位、止损线、计划买卖点、账户风险预算。

是否允许 LLM 当作事实引用：**允许，仅当用户明确输入**。不得发送到外部服务，除非用户主动复制到 ChatGPT。

### D. 手动临时证据层

内容：同花顺截图、研报摘录、新闻链接、公告 PDF 摘录、用户观察笔记、股东户数/解禁等当前权限不足数据。

是否允许 LLM 当作事实引用：**允许但需标注“手动来源/待核验”**。

### E. 系统推断/交易假设层

内容：交易环境、主升/分歧/退潮判断、Alpha/Beta 拆分、风险评分、赔率评分、交易建议。

是否允许 LLM 当作事实引用：**不允许当事实**。只能作为系统推断或交易假设，必须能追溯到事实层和辅助信号层。

## 7. 第一版开发建议

| 模块 | 依赖接口/数据 | 当前权限是否满足 | 开发复杂度 | 用户价值 | 是否推荐立即开发 |
|---|---|---:|---:|---:|---:|
| 龙虎榜事件卡 | top_list + top_inst | Yes | 中 | 高 | Yes，P0 |
| ETF 资金流卡 | etf_share_size + fund_nav + fund_daily，辅以 fund_share | Yes | 低/中 | 高 | Yes，P0 |
| 两融/资金流风险热度卡 | margin_detail + moneyflow_ths + moneyflow + 本地日K | Yes，但需节流缓存 | 中 | 高 | Yes，P1 |
| 事实时间线与 Analysis Packet | anns_d + stk_surv + stk_holdertrade + block_trade + repurchase/pledge | Yes/部分样例无数据 | 中 | 高 | Yes，P1 |

不建议第一版做：

- 股东户数自动化：权限不足；
- 限售解禁自动化：权限不足；
- 盘中 IOPV/申赎：接口未确认；
- 分钟线重构：权限不足且当前已有 AKShare；
- 全市场板块广度：工作量大，先用观察篮子和同花顺指数替代。

## 8. Analysis Packet 所需字段清单

### 8.1 单票分析包字段

| 字段 | 来源 | 时效 | 可信等级 | 当前可自动获取 | 展示方式 |
|---|---|---|---|---:|---|
| 股票代码、名称、行业、地区、上市日期 | stock_meta.parquet | 低频 | 自动事实层 | Yes | JSON + 文本 |
| 当前价、涨跌幅、成交量、市值、PE/PB、换手率、量比 | easyquotation | 秒级/30秒缓存 | 自动事实层 | Yes | 截图 + JSON |
| 日K OHLCV、成交额、换手、涨跌幅 | 本地 parquet | 日频 | 自动事实层 | Yes | 图表 + JSON 摘要 |
| MA5/10/20/30/60、RSI14、MACD | indicators.py | 日频/随K线 | 自动辅助信号层 | Yes | 截图 + JSON |
| 近 1/5/20/60 日涨跌幅、成交额变化 | 本地 parquet 计算 | 日频 | 自动辅助信号层 | 可实现 | JSON |
| 公司主营、核心产品、产业链位置、概念标签 | 公司画像 | 7日缓存/低频 | 自动事实 + 规则推断 | Yes | 文本 |
| 数据覆盖/缺失项 | data_coverage.py | 每次分析 | 系统元数据 | Yes | 文本 |
| 龙虎榜汇总与席位 | top_list/top_inst | 事件日 | 自动事实层 | Yes | 截图 + JSON |
| 两融余额及 5/20 日变化 | margin_detail | 日频 | 自动辅助信号层 | Yes，需缓存 | JSON + 风险卡 |
| 资金流分层 | moneyflow_ths/moneyflow | 日频 | 自动辅助信号层，低权重 | Yes，需缓存 | JSON + 风险卡 |
| ETF 相关字段 | etf_share_size/fund_nav/fund_daily | 日频 | 自动事实层 | 对 ETF Yes | JSON + 截图 |
| 增减持/回购/大宗/质押 | Tushare 事件接口 | 事件更新 | 自动事实层 | 部分 Yes | 事实时间线 |
| 公告标题、日期、链接 | anns_d | 事件更新 | 自动事实层 | Yes | 文本 + 链接 |
| 机构调研索引 | stk_surv | 事件更新 | 自动事实层 | Yes | 文本 |
| 股东户数 | stk_holdernumber | 不定期/季度 | 手动临时证据层 | No，权限不足 | 手动输入/截图 |
| 限售解禁 | share_float | 事件更新 | 手动临时证据层 | No，权限不足 | 手动输入 |
| 用户持仓、成本、仓位、计划 | 用户手动输入 | 实时由用户维护 | 手动账户层 | No | 不自动外传 |

### 8.2 组合分析包字段

| 字段 | 来源 | 当前状态 | 用途 |
|---|---|---|---|
| 持仓/观察池列表 | 用户手动 + 本地配置 | 需新增 | 组合驾驶舱核心 |
| 每个标的当日涨跌幅、5/20日涨跌幅 | easyquotation + 本地K线 | 可实现 | 强弱排序 |
| 行业/主题标签 | stock_meta + concept_provider | 已有 | 分组 |
| PCB 篮子表现 | 本地K线 + ETF fund_daily | 可实现 | 主题强弱 |
| 金属篮子表现 | 本地K线 + 黄金ETF + fut_daily | 可实现 | 资源股背景 |
| ETF 份额/规模变化 | etf_share_size | 可实现 | 资金流观察 |
| 两融拥挤度 | margin_detail | 可实现 | 风险预警 |
| 龙虎榜事件数量 | top_list/top_inst | 可实现 | 短线热度 |
| 公告/调研/增减持事件 | anns_d/stk_surv/stk_holdertrade | 可实现 | 事实变化 |
| 用户账户风险暴露 | 手动输入 | 不自动 | 组合风险 |

### 8.3 适合放在一张聚合截图中的字段

- 标的、名称、行业/主题；
- 当前价、日涨跌幅、5日/20日涨跌幅；
- 成交额/换手率/量比；
- 技术状态：MA20 位置、RSI、MACD 简写；
- 两融 5日/20日变化；
- 资金流 1日/5日净额；
- ETF 份额/规模 1日/5日变化；
- 最新龙虎榜/公告/调研事件标记；
- 数据缺口标记。

### 8.4 适合放在文字 Prompt / JSON 导出的字段

- 完整公司画像；
- 数据来源和日期；
- 最近 N 条龙虎榜席位；
- 最近 N 条公告标题与链接；
- 最近 N 条调研记录；
- 两融/资金流/ETF 份额序列摘要；
- 用户手动输入的交易计划；
- 系统生成的交易假设和失效条件；
- 数据可信度约束。

### 8.5 当前字段可得性总结

- 已可自动获取：行情、日K、技术指标、公司画像、龙虎榜、ETF 份额/规模/NAV/日线、两融、资金流、公告索引、调研索引、增减持、大宗交易、部分质押/回购接口结构、同花顺指数、商品期货、外汇。
- 必须手动维护：真实账户持仓/成本/仓位、交易计划、截图证据、股东户数、解禁、盘中 IOPV、公告/调研正文摘要、未验证宏观变量。
- 因权限不足不可得：`stk_holdernumber`、`share_float`、`trade_cal`、`index_daily`、`daily`、`stk_mins`。

## 9. 后续开发任务建议

### P0

1. **Tushare Token 安全迁移**：从硬编码迁移到 `.env` / 环境变量，避免日志泄露。理由：当前存在明确安全风险。
2. **Tushare 低频缓存层**：新增只读数据抓取与 parquet/JSON 缓存，统一节流。理由：多个接口 1次/分钟限制明显，不能实时批量调用。
3. **ETF 资金流卡**：基于 `etf_share_size + fund_nav + fund_daily`。理由：权限满足、用户价值高、复杂度低。
4. **龙虎榜事件卡**：基于 `top_list + top_inst`。理由：权限满足、字段完整、可直接提升单票证据页。

### P1

1. **两融风险卡**：`margin_detail` 低频缓存并计算 5/20 日变化。理由：对 PCB 强势股和资源股回撤风险有决策价值。
2. **资金流辅助卡**：`moneyflow_ths` 为主，明确低权重。理由：用户熟悉同花顺口径，但需防止过度解释。
3. **公告/调研/事件时间线**：`anns_d + stk_surv + stk_holdertrade + block_trade + repurchase + pledge`。理由：构成基本面事实层和 Analysis Packet 证据来源。
4. **Analysis Packet 导出 v1**：聚合已有行情、K线、技术、公司画像、新增事实层、数据缺口。理由：直接服务“复制给 ChatGPT”的核心场景。

### P2

1. **同花顺行业指数相对强弱**：基于 `ths_index + ths_daily`。理由：可用但需要行业映射和前端设计。
2. **观察篮子强弱系统**：PCB 篮子、金属篮子。理由：无需高权限接口，可提高组合驾驶舱价值。
3. **商品/外汇宏观变量**：`fut_daily + fx_daily`。理由：对资源股有价值，但需确认合约连续性和变量解释边界。
4. **公告 PDF/调研全文抽取**：从公告 URL 进入正文/PDF 解析。理由：价值高但复杂度高，建议在索引稳定后再做。
5. **股东户数/解禁替代来源**：权限不足时寻找其他来源或手动补录。理由：对筹码结构有价值，但当前不能自动化。
6. **分钟线重构**：暂缓。理由：Tushare 权限不足，现有 AKShare 已满足盘中展示。

## 最终核心问题回答

1. 当前 Tushare 权限实际上能支持的高价值自动化模块：龙虎榜、ETF 份额/规模/NAV/日线、两融、资金流、公告索引、机构调研索引、增减持/大宗/回购/质押低频事件、同花顺行业指数、部分商品/外汇变量。
2. 股东户数不能自动接入；龙虎榜可以；ETF 份额/规模可以；两融可以但需节流缓存；资金流可以但只能低权重使用。
3. 第一版值得开发：龙虎榜、ETF 资金流、两融/资金流风险热度、公告/调研/事件时间线与 Analysis Packet。应延后：股东户数、限售解禁、盘中 IOPV、分钟线替换、全市场板块广度。
4. 必须手动输入：真实账户持仓/成本/仓位、交易计划、股东户数、解禁、盘中 IOPV、截图证据、公告/调研正文摘要、未验证宏观变量。
5. Analysis Packet 下一版最少聚合：行情快照、日K摘要、技术指标、公司画像、数据覆盖/缺口、龙虎榜、ETF 份额/规模、两融变化、资金流低权重信号、公告/调研/事件时间线、用户手动交易计划。
6. 最省开发成本且最有决策价值路线：先做 Tushare 低频缓存层和安全 Token 配置，然后接入 ETF 资金流卡 + 龙虎榜事件卡，再补两融/资金流风险卡，最后统一输出 Analysis Packet。这样不需要大改现有 FastAPI/前端/LLM 架构，只是在现有数据覆盖度和 Prompt Builder 前增加事实聚合层。
