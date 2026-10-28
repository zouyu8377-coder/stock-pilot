# 无网页数据维护

## 定位

数据收集由普通 Python/Windows 任务完成，不消耗模型 token，不依赖前端、
Uvicorn、API 端口或 Codex 是否打开。外部模型只在用户发起讨论时参与。
电脑关机、休眠或用户注销时不运行；不唤醒电脑、不保存登录密码。

## 已覆盖与边界

| 数据 | 无网页更新方式 | 限制 |
| --- | --- | --- |
| 持仓/观察标的与轮动代理日K | BaoStock，先核对交易日历，逐文件核验日期 | 停牌、接口延迟、缺失文件单列失败，不把空增量当成功 |
| 当前持仓/观察标的行情 | 腾讯报价，独立于日K保存 | 包含市场时间和抓取时间；禁止模拟行情；失败不冒充实时 |
| MA、收益、均量、相对前5完整交易日量能 | 本地完整日K确定性计算 | 日K与盘中数据不混为同日收盘证据 |
| 公告/财报 | 巨潮近90日、最多2页索引及每股票2份PDF选段 | 非完整公告库；扫描PDF需另做OCR；无AI核验结论 |
| 狭义广度（重点资料覆盖） | 持仓/关注标的时效 + 重要参考组时效 | 已上市持仓日K均须有效、关注池至少80%；盘中另检查15分钟内报价；境内大盘、纳指、美元、黄金、有色各有有效参考。与涨跌家数不是同一个指标 |
| 重要参考指数/代理 | 沪指、沪深300本地日K；纳指/美元Yahoo延迟参考；黄金/有色ETF或期货代理 | 海外按源交易时段检查；无明确时段时采用48/96小时观测时效，不声称认证海外节假日日历；代理不冒充现货指数 |
| 广义广度（全市场） | 全市场股票日K聚合，单独展示覆盖率 | 全量不足不拖低狭义健康灯，样本不当作交易所全量 |
| 黄金/铜参考 | 复用 Yahoo COMEX 延时报价 | 非实时或官方结算，受网络/限流影响 |
| 宏观发布线索 | Fed/BLS 官方RSS | 标题与发布日期，不等于全文分析或未来事件日历 |
| 持仓台账 | 只读已有用户确认数据 | 不接券商；不能知道未上传的新交易 |

未来宏观事件日历、地缘新闻、行业新闻与完整结构化财报指标仍有缺口，
不能因为“任务已执行”宣称全部具备。股票停牌与取数故障需进一步区分。
普通截图识图和投资解释需要模型，不属于此后台任务。

## 使用

在任意目录运行，脚本会固定切换到本项目 backend，避免写入另一个台账：

```powershell
C:/Python312/python.exe C:/Project/Stock-Pilot/backend/scripts/sync_data.py
C:/Python312/python.exe C:/Project/Stock-Pilot/backend/scripts/sync_data.py --status
C:/Python312/python.exe C:/Project/Stock-Pilot/backend/scripts/sync_data.py --stages market --force
C:/Python312/python.exe C:/Project/Stock-Pilot/backend/scripts/sync_data.py --prepare-discussion
```

`--force` 仅绕过抓取间隔，不绕过锁、数据校验或用户确认。
退出码 0=完整或另一实例运行，2=部分来源失败/未收集，1=启动/交接错误。
刷新交接必须显式请求；后台定时更新不会覆盖进行中的讨论、回传和补充请求。
交接仍使用既有 JSON Schema；历史补充材料保留原日期，不伪装成新证据。

```powershell
./scripts/manage_data_sync.ps1 -Action Install -PythonPath C:/Python312/python.exe
./scripts/manage_data_sync.ps1 -Action Status
./scripts/manage_data_sync.ps1 -Action Run -PythonPath C:/Python312/python.exe
./scripts/manage_data_sync.ps1 -Action Remove
```

任务 `StockPilot-ObjectiveDataSync` 在当前用户登录和每30分钟触发，普通权限、
隐藏窗口。按来源缓存：日K/轮动1小时、广度6小时，公告6小时，公开宏观/商品1小时；
行情盘中15分钟、非盘中6小时；失败15分钟后允许重试。新日期或新标的绕过旧TTL。
后台采集不启动前端，也不启用旧的模型自动巡检。
正式后端启动默认发起一次相同的无模型同步（`STOCK_PILOT_AUTO_DATA_SYNC=0`可关闭），不再受旧模型自动化总开关控制。
顺序为重点日K/行情/参考数据优先，随后财报、行业与宏观，再进行全市场分批补齐和广度重建。
全市场按本地股票及ETF元数据范围，每轮最多200个标的、最长300秒，`backfill_cursor.json`保存已核验日期和尝试记录；失败标的至少隔一小时重试。
每次程序启动以及已有每30分钟任务会继续下一批，重启不从头重复下载。并非保证单次启动完成所有历史数据；过期、停牌、网络失败仍需显示。
单轮同步总预算20分钟，未执行来源保留旧缓存与延期状态，下一轮继续，避免越过现有Windows任务的25分钟执行上限。
分析侧的`scope=tracked`不会等待全市场续传。后台批次与网页取数共用同步锁，重复任务跳过而非并发；源缓存命中也会跳过下载。

## 数据与可靠性

固定私有目录 `backend/data/data_sync/` 已 gitignore：

- `latest.json`：账户与每个来源的最近一次结果，供外部讨论读取。
- `status.json`：阶段、进度、心跳、开始/结束时间、失败状态。
- `<stage>.json` 与 `<stage>.last_success.json`：最近尝试和上次完整成功，旧成功不冒充本次成功。
- `documents/`：按股票和公告ID缓存提取正文，同一报告不反复下载解析。
- `worker.log` / `worker.previous.log`：限制轮转大小，不向桌面或项目根目录导出。
- `references.json`：重要指数与显式ETF/期货代理的观测时间和逐项失败。
- `startup.json` / `startup.log`：正式服务启动采集的进程与日志，不含模型调用。
- `backfill.json` / `backfill_cursor.json`：全市场批次结果与续传游标，不是持仓台账。

OS 文件锁避免两个同步实例并发；冷数据与原 worker 共用更新锁。
新锁记录进程ID，确认进程已退出才允许回收；无进程信息的旧锁不擅自删除。
各阶段独立子进程与时限，卡住的来源不会阻塞所有后续来源；超时保留阶段进度。
同一组阶段不会创建逐次导出目录或无限归档。API运行时也可用
`GET /api/system/data-sync-status` 读取同一状态。
回传讨论结果仍需用户确认，不会自动修改账户或下单。

## 测试

```powershell
cd backend
C:/Python312/python.exe -m pytest tests/test_headless_data_sync.py tests/test_external_discussion.py -q
```

单元测试使用临时目录和模拟取数，不连接模型、不修改真实账户。
