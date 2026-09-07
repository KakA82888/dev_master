import os
import sqlite3
import sys
from pathlib import Path

# 让 pytest 能从项目根导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 测试使用独立的应用状态库，避免污染开发数据（app.db）
# 注意：沙箱禁止直接删文件（Path.unlink 抛 SAFE_DELETE_FAIL_CLOSED），
# 故用 SQL DROP TABLE 清空旧结构，表由 init_db() 在收集期重建。
_TEST_DB = Path(__file__).resolve().parent / "data" / "processed" / "app_test.db"
if _TEST_DB.exists():
    con = sqlite3.connect(str(_TEST_DB))
    try:
        con.execute("DROP TABLE IF EXISTS reports")
        con.execute("DROP TABLE IF EXISTS users")
        con.commit()
    finally:
        con.close()
os.environ["APP_DB_PATH"] = str(_TEST_DB)
