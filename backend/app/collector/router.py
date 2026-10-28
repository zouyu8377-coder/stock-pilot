from app.collector.realtime.easyquotation_provider import EasyQuotationProvider, LocalColdQuoteProvider
from app.collector.realtime.mock_provider import MockRealtimeProvider
from app.collector.history.base_market_provider import BaseMarketProvider


class CollectorRouter:
    """
    统一的数据入口
    - success-first stop
    - provider failover
    """

    def __init__(self, *, allow_mock: bool = False):
        self.providers = [
            EasyQuotationProvider(),
            LocalColdQuoteProvider(),
        ]
        if allow_mock:
            self.providers.append(MockRealtimeProvider())
        self.history_provider = BaseMarketProvider()

    def get_quote(self, symbol: str):
        last_error = None
        for provider in self.providers:
            try:
                return provider.get_quote(symbol)
            except Exception as e:
                print(f"{provider.__class__.__name__} failed: {e}")
                last_error = e
                continue
        raise last_error

    def get_history(self, symbol: str, limit: int = 5000):
        return self.history_provider.get_daily_history(symbol, limit)


collector = CollectorRouter()
