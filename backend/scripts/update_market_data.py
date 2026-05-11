"""
手动执行冷数据增量更新脚本。
复用 app.core.data_updater 的核心逻辑。
"""
import sys
from pathlib import Path

# 将 backend 加入路径，确保能 import app
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.data_updater import get_last_trading_date, run_sync_update


def main():
    target_date = get_last_trading_date()
    print(f"=== 手动触发增量更新，目标日期: {target_date} ===")
    result = run_sync_update(target_date)
    print("=== 更新摘要 ===")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
