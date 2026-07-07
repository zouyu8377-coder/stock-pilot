import tushare as ts
import pandas as pd

from app.core.config import settings
from app.tushare.exceptions import TushareConfigError


class TushareProvider:
    """
    从 Tushare 获取公司基本面数据。
    失败时返回空字典，不抛异常。
    """

    def __init__(self):
        token = settings.TUSHARE_TOKEN.strip()
        if not token:
            self.pro = None
            return
        ts.set_token(token)
        self.pro = ts.pro_api()

    def _require_client(self):
        if self.pro is None:
            raise TushareConfigError("Tushare token is not configured. Set backend env var TUSHARE_TOKEN.")
        return self.pro

    def _convert_symbol(self, symbol: str) -> str:
        symbol = symbol.zfill(6)
        if symbol.startswith("6"):
            return f"{symbol}.SH"
        elif symbol.startswith("0") or symbol.startswith("3"):
            return f"{symbol}.SZ"
        return f"{symbol}.SH"

    def get_company_info(self, symbol: str) -> dict:
        """
        返回字段:
        - main_business: 主营业务
        - introduction: 公司简介
        - reg_capital: 注册资本
        - city: 所在城市
        """
        ts_code = self._convert_symbol(symbol)
        result = {}

        try:
            df = self._require_client().stock_company(ts_code=ts_code)
            if df is not None and not df.empty:
                row = df.iloc[0]
                result["main_business"] = row.get("main_business", "")
                result["introduction"] = row.get("introduction", "")
                result["reg_capital"] = row.get("reg_capital", "")
                result["city"] = row.get("city", "")
        except TushareConfigError as e:
            print(f"[TushareProvider] {e}")
        except Exception as e:
            print(f"[TushareProvider] stock_company failed for {symbol}: {e}")

        return result

    def get_latest_fina_indicator(self, symbol: str) -> dict:
        """
        返回最新一期财务指标关键字段。
        """
        ts_code = self._convert_symbol(symbol)
        result = {}

        try:
            df = self._require_client().fina_indicator(ts_code=ts_code, limit=1)
            if df is not None and not df.empty:
                row = df.iloc[0]
                result["roe"] = row.get("roe", "")
                result["grossprofit_margin"] = row.get("grossprofit_margin", "")
                result["debt_to_assets"] = row.get("debt_to_assets", "")
        except TushareConfigError as e:
            print(f"[TushareProvider] {e}")
        except Exception as e:
            print(f"[TushareProvider] fina_indicator failed for {symbol}: {e}")

        return result
