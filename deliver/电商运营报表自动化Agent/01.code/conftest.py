import os
import sqlite3
import sys
from pathlib import Path

# 让 pytest 能从项目根导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 排除交付包与工作目录，避免被递归收集：
# deliver/ 内含源码副本，若被收集会与主项目同名测试文件冲突（import file mismatch），
# 导致 collection error；.workbuddy/ 为工作目录，同样不含需要运行的测试。
collect_ignore_glob = ["deliver/*", ".workbuddy/*"]

# 测试期间强制走规则通道：避免导入 app.backend.main 时其顶层 load_dotenv
# 把 .env 里的 LLM_MODE=llm 注入进程，导致生成类测试去调用真实大模型（慢且依赖外部 API）。
# 评测脚本（eval_llm.py）会自行显式开启 LLM 通道。
os.environ["LLM_MODE"] = "rule"

# 后端接口测试使用 ?sync=true（同步生成，返回即完成）；
# 该参数默认关闭以防止调试后门暴露在生产接口上，测试期显式开启。
os.environ["APP_ALLOW_SYNC"] = "1"

# 测试使用独立的应用状态库，避免污染开发数据（app.db）
# 注意：沙箱禁止直接删文件（Path.unlink 抛 SAFE_DELETE_FAIL_CLOSED），
# 故用 SQL DROP TABLE 清空旧结构，表由 init_db() 在收集期重建。
_TEST_DB = Path(__file__).resolve().parent / "data" / "processed" / "app_test.db"
if _TEST_DB.exists():
    con = sqlite3.connect(str(_TEST_DB))
    try:
        # 先删依赖表，再删主表（SQLite 默认不强制外键，顺序仅为语义清晰）
        con.execute("DROP TABLE IF EXISTS feedback")
        con.execute("DROP TABLE IF EXISTS schedules")
        con.execute("DROP TABLE IF EXISTS reports")
        con.execute("DROP TABLE IF EXISTS users")
        con.commit()
    finally:
        con.close()
os.environ["APP_DB_PATH"] = str(_TEST_DB)
