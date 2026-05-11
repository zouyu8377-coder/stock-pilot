import random


class MockRealtimeProvider:
    """
    临时模拟实时行情
    后续替换为 easyquotation
    """

    def get_quote(self, symbol: str):
        price = round(random.uniform(10, 100), 2)

        return {
            "symbol": symbol,
            "price": price,
            "change_pct": round(random.uniform(-3, 3), 2),
            "hot_status": "ready",
            "provider": "mock",
        }