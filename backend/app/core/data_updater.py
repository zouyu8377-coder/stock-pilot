import asyncio
import json
import pandas as pd
import akshare as ak
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import Optional

BASE_DIR = Path(__file__).resolve().parents[2]
BASE_MARKET_DIR = BASE_DIR / "data" / "base_market"
STATUS_FILE = BASE_DIR / "data" / "update_status.json"


def get_last_trading_date(ref_date: Optional[date] = None) -> date:
    """
    计算上一A股交易日。
    当前版本仅排除周末，不排法定节假日（后续可接入交易日历）。
    """
    d = ref_date or date.today()
    weekday = d.weekday()  # 0=周一, 5=周六, 6=周日

    if weekday == 5:       # 周六 -> 周五
        return d - timedelta(days=1)
    elif weekday == 6:     # 周日 -> 周五
        return d - timedelta(days=2)
    elif weekday == 0:     # 周一 -> 上周五
        return d - timedelta(days=3)
    else:
        return d - timedelta(days=1)


def load_update_status() -> dict:
    if not STATUS_FILE.exists():
        return {
            "last_trading_date": None,
            "completed_count": 0,
            "total_symbols": 0,
            "updated_at": None,
        }
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "last_trading_date": None,
            "completed_count": 0,
            "total_symbols": 0,
            "updated_at": None,
        }


def save_update_status(status: dict) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def extract_symbol(path: Path) -> str:
    filename = path.stem
    if "." in filename:
        return filename.split(".", 1)[1]
    return filename


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    col_map = {
        "日期": "date",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
    }
    rename_map = {cn: en for cn, en in col_map.items() if cn in df.columns}
    if rename_map:
        df = df.rename(columns=rename_map)
    return df


def fetch_increment(symbol: str, start_date: str) -> Optional[pd.DataFrame]:
    """使用 akshare 获取增量历史数据"""
    start = datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=1)
    start_str = start.strftime("%Y-%m-%d")
    end_str = datetime.now().strftime("%Y-%m-%d")

    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        adjust="qfq",
        start_date=start_str,
        end_date=end_str,
    )

    if df is None or df.empty:
        return None

    df = normalize_columns(df)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def is_symbol_updated(path: Path, target_date: date) -> bool:
    """检查单只股票的 parquet 是否已包含 target_date 的数据"""
    try:
        df = pd.read_parquet(path)
        date_col = "date" if "date" in df.columns else "日期"
        df[date_col] = pd.to_datetime(df[date_col])
        last_date = df[date_col].max().date()
        return last_date >= target_date
    except Exception:
        return False


def check_update_status(target_date: date) -> tuple[bool, list[str], int]:
    """
    检查全部股票是否已更新到 target_date。
    返回: (是否全部更新, 未更新股票代码列表, 总股票数)
    """
    if not BASE_MARKET_DIR.exists():
        return False, [], 0

    files = list(BASE_MARKET_DIR.glob("*.parquet"))
    total = len(files)

    outdated = []
    for path in files:
        if not is_symbol_updated(path, target_date):
            symbol = extract_symbol(path)
            outdated.append(symbol)

    all_updated = len(outdated) == 0
    return all_updated, outdated, total


def update_single_symbol(path: Path, target_date: date) -> bool:
    """增量更新单只股票到 target_date"""
    symbol = extract_symbol(path)
    try:
        old_df = pd.read_parquet(path)
        date_col = "date" if "date" in old_df.columns else "日期"
        old_df[date_col] = pd.to_datetime(old_df[date_col])
        last_date = old_df[date_col].max().strftime("%Y-%m-%d")

        new_df = fetch_increment(symbol, last_date)
        if new_df is None or new_df.empty:
            return True

        combined = pd.concat([old_df, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["date"])
        combined = combined.sort_values("date")
        combined.to_parquet(path)
        return True
    except Exception as e:
        print(f"[DataUpdater] FAILED {symbol}: {e}")
        return False


def run_sync_update(target_date: date) -> dict:
    """
    同步执行全量增量更新。
    返回摘要信息。
    """
    print(f"[DataUpdater] 开始增量更新，目标日期: {target_date}")

    all_updated, outdated, total = check_update_status(target_date)
    if all_updated:
        print(f"[DataUpdater] 所有 {total} 只股票已更新到 {target_date}")
        save_update_status({
            "last_trading_date": target_date.isoformat(),
            "completed_count": total,
            "total_symbols": total,
            "updated_at": datetime.now().isoformat(),
        })
        return {"action": "none", "total": total, "updated": 0, "failed": 0}

    print(f"[DataUpdater] 需要更新 {len(outdated)}/{total} 只股票")

    updated_count = 0
    failed_count = 0
    completed = []

    files = list(BASE_MARKET_DIR.glob("*.parquet"))
    for idx, path in enumerate(files):
        symbol = extract_symbol(path)
        if symbol not in outdated:
            continue

        success = update_single_symbol(path, target_date)
        if success:
            updated_count += 1
            completed.append(symbol)
        else:
            failed_count += 1

        # 每 100 只输出一次进度
        if (updated_count + failed_count) % 100 == 0:
            print(f"[DataUpdater] 进度: {updated_count + failed_count}/{len(outdated)}")

    save_update_status({
        "last_trading_date": target_date.isoformat(),
        "completed_count": updated_count,
        "total_symbols": total,
        "updated_at": datetime.now().isoformat(),
    })

    print(f"[DataUpdater] 更新完成: +{updated_count}, 失败: {failed_count}")
    return {
        "action": "updated",
        "total": total,
        "updated": updated_count,
        "failed": failed_count,
        "target_date": target_date.isoformat(),
    }


async def check_and_update() -> None:
    """
    入口函数：检查数据更新状态，如未更新则在后台执行增量更新。
    设计为 FastAPI startup 事件调用。
    """
    target_date = get_last_trading_date()
    status = load_update_status()

    # 如果状态文件显示已更新到 target_date，直接跳过
    if status.get("last_trading_date") == target_date.isoformat():
        total = status.get("total_symbols", 0)
        print(f"[DataUpdater] 数据已更新到 {target_date}，共 {total} 只")
        return

    all_updated, outdated, total = check_update_status(target_date)
    if all_updated:
        print(f"[DataUpdater] 校验通过：所有 {total} 只股票已更新到 {target_date}")
        save_update_status({
            "last_trading_date": target_date.isoformat(),
            "completed_count": total,
            "total_symbols": total,
            "updated_at": datetime.now().isoformat(),
        })
        return

    print(f"[DataUpdater] 数据未更新，需要更新 {len(outdated)}/{total} 只，后台执行...")

    # 在线程池中执行同步的 akshare 调用，避免阻塞事件循环
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_sync_update, target_date)
