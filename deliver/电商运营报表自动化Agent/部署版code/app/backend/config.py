"""后端配置：路径、密钥、JWT 参数。"""
import os
from pathlib import Path
from datetime import timedelta

# 项目根目录：app/backend/config.py -> app -> 电商
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 唯一事实表所在库（只读查询，由 S1 指标内核产出）
DATA_DB_PATH = PROJECT_ROOT / "data" / "processed" / "report_agent.db"
# 应用状态库（用户 / 报告记录），与事实表分离，保证金额对账纪律不被污染
# 可用环境变量 APP_DB_PATH 覆盖（测试时指向独立库，避免污染开发数据）
APP_DB_PATH = Path(os.getenv("APP_DB_PATH", str(PROJECT_ROOT / "data" / "processed" / "app.db")))

# 鉴权
SECRET_KEY = os.getenv("APP_SECRET_KEY", "dev-secret-change-me-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = timedelta(hours=24)

# 演示用种子账号（首次启动自动创建；生产环境请删除或改密）
SEED_USERNAME = os.getenv("SEED_USERNAME", "demo")
SEED_PASSWORD = os.getenv("SEED_PASSWORD", "demo1234")
