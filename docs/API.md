# API 文档

## 基础信息

- 基础地址：`http://127.0.0.1:8000`
- CORS：开发环境允许所有来源
- 健康检查：`GET /health`

## 接口列表

### 1. 分析股票（主接口）

```http
POST /api/analyze
```

请求体：

```json
{
  "symbols": ["600519", "300750"]
}
```

响应：

```json
{
  "status": "success",
  "stocks": [
    {
      "symbol": "600519",
      "name": "贵州茅台",
      "price": 1372.99,
      "change_pct": 0.14,
      "volume": 3336900,
      "provider": "easyquotation",
      "hot_status": "ready",
      "cold_status": "ready",
      "ai_status": "ready",
      "history_ready": true,
      "industry": "白酒",
      "area": "贵州",
      "market_cap": 21000.5,
      "pe": 28.5,
      "pb": 8.2,
      "turnover_rate": 0.35,
      "indicators": {
        "ma5": 1381.0,
        "ma10": 1400.02,
        "ma20": 1421.52,
        "ma30": 1425.15,
        "ma60": 1427.81,
        "rsi14": 27.44,
        "macd": -16.49
      },
      "analysis": {
        "trend": "偏空",
        "signal": "观望",
        "support": "1370/1350",
        "resistance": "1381/1400",
        "summary": "短线超卖但趋势偏弱，等待企稳信号"
      }
    }
  ]
}
```

### 2. 获取历史 K 线

```http
GET /api/history/{symbol}?limit=250
```

参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| symbol | string | - | 股票代码，如 `600519` |
| limit | int | 250 | 返回最近 N 条，范围 10-5000 |

响应：

```json
[
  {
    "date": "2024-01-02",
    "open": 1720.0,
    "high": 1735.0,
    "low": 1715.0,
    "close": 1730.0,
    "ma5": 1725.5,
    "ma10": 1710.2,
    "ma20": 1705.0,
    "ma30": null,
    "ma60": null
  }
]
```

### 3. 获取分时数据

```http
GET /api/intraday/{symbol}
```

响应：分时数据数组（格式取决于数据源）。

### 4. AI 深度分析

```http
GET /api/deep-analyze/{symbol}
```

响应：

```json
{
  "success": true,
  "data": {
    "market_state": "震荡偏弱",
    "short_term": "观望",
    "medium_term": "偏空",
    "long_term": "偏多",
    "industry_analysis": "白酒行业...",
    "risk_factors": ["库存压力", "消费疲软"],
    "key_observations": ["北向资金连续流出"],
    "summary": "短期承压，长期品牌护城河稳固",
    "core_conflict": "估值修复 vs 业绩增速放缓",
    "expectation_gap": "市场对中秋旺季预期过低",
    "fund_flow_analysis": "机构减仓，散户承接",
    "bullish_triggers": ["旺季动销超预期"],
    "bearish_triggers": ["批价持续下行"],
    "risk_reward_assessment": "当前赔率中等，胜率偏低"
  }
}
```

## 错误处理

所有接口在出错时返回适当的 HTTP 状态码和错误信息。`deep-analyze` 接口在失败时返回：

```json
{
  "success": false,
  "message": "AI分析超时: ..."
}
```
