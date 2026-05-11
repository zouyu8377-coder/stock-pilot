1. 项目目标

Stock-Pilot 是一个个人使用的 A 股智能分析助手。

核心目标：

输入股票代码
实时获取行情（Hot Data）
读取本地历史数据库（Cold Data）
自动计算技术指标
调用 LLM 生成简洁投资分析
返回统一 JSON，供前端展示

定位：

不是交易系统
不是量化回测平台
是一个“增强版股票观察与分析工具”

2. 当前整体架构
Frontend (Vue3)
    ↓ HTTP
FastAPI API Layer
    ↓
Collector Router
 ├── Hot Provider (easyquotation)
 ├── Cold Provider (BaseMarketProvider)
 ├── Cache Manager
 ├── Indicator Engine
 └── AI Analyzer
3. 数据流设计
Hot Path（实时路径）

用途：

获取当前行情。

数据源：

easyquotation

特点：

快
秒级
可高频调用
适合实时刷新

获取字段：

最新价
涨跌幅
成交量
开盘价
最高价
最低价
买卖盘信息

缓存策略：

内存缓存
TTL = 10~30 秒

状态：

"hot_status": "ready"
Cold Path（历史路径）

用途：

提供历史 K 线和技术指标计算基础。

当前数据源：

backend/data/base_market/*.parquet

来源：

bootstrap_market_data.py

一次性批量下载的 A 股历史数据库。

不再依赖实时调用 AkShare。

优点：

本地读取快
稳定
无接口限制
可扩展到全市场

状态：

"cold_status": "ready"
"history_ready": true
4. 缓存系统（Cache Manager）

路径：

backend/app/cache/manager.py

职责：

Hot Cache

缓存实时行情。

key = symbol
ttl = 10~30s

日志：

HOT CACHE MISS
HOT CACHE HIT

作用：

避免重复请求 easyquotation。

Cold Cache（下一步可增强）

目前：

本地 parquet 即可满足需求。

未来可增加：

indicator cache
AI result cache
5. 技术指标系统

路径：

backend/app/analysis/indicators.py

当前支持：

均线
MA10
MA30
EMA20
EMA60
动量指标
RSI14
MACD

输入：

history dataframe

输出：

{
  "ma10": 1400.02,
  "ma30": 1425.15,
  "ema20": 1410.36,
  "ema60": 1427.81,
  "rsi14": 27.44,
  "macd": -16.49
}

实现方式：

pandas_ta

说明：

已处理字段兼容：

close
收盘
6. AI 分析层

路径：

backend/app/ai/

模块：

prompt_builder.py

负责构造 LLM Prompt。

输入：

股票名称
当前价格
涨跌幅
技术指标

输出：

自然语言分析请求。

llm_client.py

负责调用兼容 OpenAI API 的模型接口。

当前支持：

OpenAI-compatible API

配置：

LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
analyzer.py

负责：

调用 prompt_builder
调用 llm_client
解析 JSON
返回结构化分析结果

输出格式：

{
  "trend": "偏空",
  "signal": "超卖",
  "support": "1370",
  "resistance": "1400",
  "summary": "RSI超卖或有短线反弹，但趋势偏弱，关注1400压力，未企稳前暂观望。"
}

状态：

"ai_status": "ready"
7. API 当前返回结构

接口：

POST /api/analyze

响应：

{
  "status": "success",
  "stocks": [
    {
      "symbol": "600519",
      "price": 1372.99,
      "change_pct": 0.14,
      "name": "贵州茅台",
      "volume": 3336900,
      "provider": "easyquotation",
      "hot_status": "ready",
      "cold_status": "ready",
      "ai_status": "ready",
      "history_ready": true,
      "indicators": {},
      "analysis": {}
    }
  ]
}