from pathlib import Path

# ====== project paths ======
BASE_DIR = Path(__file__).resolve().parent.parent

MART_WEEKLY_DIR = BASE_DIR / "Processed" / "mart_weekly"          # 仍保留（排名表可能还需要）
MART_MONTHLY_DIR = BASE_DIR / "Processed" / "mart_monthly"        # 仍保留（备用）
MART_DAILY_ROLLING_DIR = BASE_DIR / "Processed" / "mart_daily_rolling"   # 新增

# ====== guards ======
PRICE_MAX = 100_000_000
PRICE_MIN_EXCLUSIVE = 0

# rolling windows (in weeks) – 可能不再使用，但保留
ROLL_WINDOWS = {
    "roll4": 4,
    "roll13": 13,
    "roll26": 26,
}

# ====== ranking config ======
TOP_N_RANK = 5

# sales thresholds to reduce noise
MIN_SALES_STABLE_MOM = 10
MIN_SALES_STABLE_QOQ = 30