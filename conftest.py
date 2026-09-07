import os
import sys
from pathlib import Path

# 让 pytest 能从项目根导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 测试使用独立的应用状态库，避免污染开发数据（app.db）
_TEST_DB = Path(__file__).resolve().parent / "data" / "processed" / "app_test.db"
if _TEST_DB.exists():
    _TEST_DB.unlink()
os.environ["APP_DB_PATH"] = str(_TEST_DB)
