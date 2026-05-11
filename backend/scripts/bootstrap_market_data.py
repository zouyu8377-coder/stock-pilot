from pathlib import Path
import json
import time
import datetime
import pandas as pd
import baostock as bs


# ============================================================
# 路径配置（修复 backend/backend 问题）
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "base_market"
META_DIR = BASE_DIR / "data" / "metadata"

PROGRESS_FILE = META_DIR / "bootstrap_progress.json"
FAILED_FILE = META_DIR / "failed_symbols.json"
SUMMARY_FILE = META_DIR / "market_summary.json"


# ============================================================
# 初始化目录
# ============================================================

def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# BaoStock 登录
# ============================================================

def login():
    lg = bs.login()

    if lg.error_code != "0":
        raise Exception(
            f"Baostock login failed: {lg.error_msg}"
        )

    print("Baostock login OK")


def logout():
    bs.logout()
    print("logout success!")


# ============================================================
# 证券过滤
# A股 + ETF + LOF
# ============================================================

def is_target_security(code: str) -> bool:
    prefixes = [
        # ----------------
        # A股
        # ----------------
        "sh.600",
        "sh.601",
        "sh.603",
        "sh.605",
        "sh.688",

        "sz.000",
        "sz.001",
        "sz.002",
        "sz.300",

        # ----------------
        # ETF
        # ----------------
        "sh.510",
        "sh.511",
        "sh.512",
        "sh.513",
        "sh.515",
        "sh.518",

        "sz.159",

        # ----------------
        # LOF
        # ----------------
        "sz.160",
        "sz.161",
        "sz.162",
        "sz.163",
        "sz.164",
        "sz.165",
        "sz.166",
    ]

    return any(code.startswith(p) for p in prefixes)


# ============================================================
# 获取证券列表
# ============================================================

def load_stock_list():
    print("获取证券列表...")

    rs = bs.query_stock_basic()

    if rs is None:
        raise Exception(
            "query_stock_basic returned None"
        )

    if rs.error_code != "0":
        raise Exception(
            f"query_stock_basic failed: {rs.error_msg}"
        )

    securities = []

    while rs.next():
        row = rs.get_row_data()
        code = row[0]

        if is_target_security(code):
            securities.append(code)

    securities = sorted(set(securities))

    print(
        f"过滤后目标证券数量: {len(securities)}"
    )

    return securities


# ============================================================
# Progress
# ============================================================

def load_progress():
    if not PROGRESS_FILE.exists():
        return {
            "completed": [],
            "completed_count": 0,
            "updated_at": None,
        }

    with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_progress(symbol, progress):
    progress["completed"].append(symbol)
    progress["completed_count"] = len(
        progress["completed"]
    )
    progress["updated_at"] = (
        datetime.datetime.now().isoformat()
    )

    with open(
        PROGRESS_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            progress,
            f,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# Failure
# ============================================================

def record_failure(symbol):
    failures = []

    if FAILED_FILE.exists():
        with open(
            FAILED_FILE,
            "r",
            encoding="utf-8",
        ) as f:
            failures = json.load(f)

    if symbol not in failures:
        failures.append(symbol)

    with open(
        FAILED_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            failures,
            f,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# 下载单个证券
# ============================================================

def download_symbol(symbol):
    file_path = DATA_DIR / f"{symbol}.parquet"

    # 已存在则跳过
    if file_path.exists():
        return True

    for i in range(3):
        try:
            rs = bs.query_history_k_data_plus(
                code=symbol,
                fields=(
                    "date,"
                    "open,"
                    "high,"
                    "low,"
                    "close,"
                    "volume,"
                    "amount,"
                    "turn,"
                    "pctChg"
                ),
                start_date="1990-01-01",
                end_date=str(
                    datetime.date.today()
                ),
                frequency="d",
                adjustflag="3",
            )

            if rs is None:
                raise Exception(
                    "query returned None"
                )

            if rs.error_code != "0":
                raise Exception(
                    rs.error_msg
                )

            rows = []

            while rs.next():
                rows.append(
                    rs.get_row_data()
                )

            # 空数据：直接跳过
            if len(rows) == 0:
                print(
                    f"{symbol} 无历史数据，跳过"
                )
                return True

            df = pd.DataFrame(
                rows,
                columns=[
                    "date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "amount",
                    "turn",
                    "pctChg",
                ],
            )

            df.to_parquet(
                file_path,
                index=False,
            )

            return True

        except Exception as e:
            print(
                f"retry {i+1}/3 "
                f"failed {symbol}: {e}"
            )
            time.sleep(1)

    return False


# ============================================================
# Summary
# ============================================================

def get_folder_size(path: Path):
    total = 0

    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size

    return total


def update_summary(
    total,
    downloaded,
    failed,
):
    summary = {
        "total_symbols": total,
        "downloaded": downloaded,
        "failed": failed,
        "disk_usage_gb": round(
            get_folder_size(DATA_DIR)
            / 1024**3,
            2,
        ),
        "updated_at":
            datetime.datetime.now()
            .isoformat(),
    }

    with open(
        SUMMARY_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            summary,
            f,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# Main
# ============================================================

def main():
    ensure_dirs()

    print(
        "=== A股历史数据 Bootstrap 开始 ==="
    )

    login()

    stock_list = load_stock_list()

    progress = load_progress()

    completed = set(
        progress.get("completed", [])
    )

    print(
        f"断点续跑："
        f"已完成 {len(completed)}"
    )

    downloaded = len(completed)
    failed = 0

    try:
        for i, symbol in enumerate(
            stock_list
        ):
            if symbol in completed:
                continue

            print(
                f"[{i+1}/"
                f"{len(stock_list)}] "
                f"{symbol}"
            )

            ok = download_symbol(symbol)

            if ok:
                save_progress(
                    symbol,
                    progress,
                )
                downloaded += 1
                print(
                    f"{symbol} OK"
                )
            else:
                record_failure(
                    symbol
                )
                failed += 1
                print(
                    f"{symbol} FAILED"
                )

            time.sleep(0.3)

    except KeyboardInterrupt:
        print(
            "用户中断，保存进度..."
        )

    finally:
        logout()

        update_summary(
            total=len(stock_list),
            downloaded=downloaded,
            failed=failed,
        )

        print(
            "=== Bootstrap 完成 ==="
        )
        print(
            f"总计: "
            f"{len(stock_list)}"
        )
        print(
            f"下载: "
            f"{downloaded}"
        )
        print(
            f"失败: "
            f"{failed}"
        )


if __name__ == "__main__":
    main()