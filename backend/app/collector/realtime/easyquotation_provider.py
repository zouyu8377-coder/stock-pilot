import easyquotation


class EasyQuotationProvider:
    """
    腾讯实时行情 provider
    """

    def __init__(self):
        self.client = easyquotation.use("tencent")

    def get_quote(self, symbol: str):
        """
        symbol 示例:
        600519
        300750
        000001
        """
        data = self.client.real(symbol)

        if not data:
            raise ValueError("easyquotation returned empty data")

        if symbol not in data:
            raise ValueError(f"Quote not found: {symbol}")

        q = data[symbol]

        return {
            "symbol": symbol,
            "price": q.get("now"),
            "change_pct": q["涨跌(%)"],
            "name": q.get("name"),
            "volume": q.get("volume"),
            "provider": "easyquotation",
            "hot_status": "ready",
            # A股常用指标
            "market_cap": q.get("总市值") or q.get("市值"),
            "float_market_cap": q.get("流通市值") or q.get("流通市值"),
            "pe": q.get("PE") or q.get("市盈率"),
            "pb": q.get("PB") or q.get("市净率"),
            "turnover_rate": q.get("turnover") or q.get("换手率") or q.get("换手"),
            "volume_ratio": q.get("量比"),
        }