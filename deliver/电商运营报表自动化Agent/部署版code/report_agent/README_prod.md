# 电商运营报表自动化 Agent —— 生产部署文档（README_prod）

| 项 | 内容 |
|---|---|
| 版本 / 日期 | v1.0 / 2026-09-10 |
| 适用 | 部署人员：将系统部署到服务器，单端口对外提供服务 |
| 特点 | **已内置前端构建产物**（`backend/static/`），无需 Node.js 环境 |

---

## 一、目录说明

```
部署版code/report_agent/
└── backend/
    ├── app/              FastAPI 源码（含 routers / models / services）
    ├── static/           前端构建产物（Vite build 输出，已内置）
    ├── requirements.txt  Python 依赖
    └── .env.example      环境配置模板
```

> 与开发版的区别：本目录**已包含前端 dist**，后端启动后访问 `http://<host>:8000` 即为完整应用，服务器上不需要安装 Node.js。

## 二、部署步骤

```bash
# 1) 安装 Python 依赖
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2) 配置环境变量
cp .env.example .env
#    生产环境必须修改：APP_SECRET_KEY、SEED_PASSWORD
#    如需大模型解析：填 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL，并设 LLM_MODE=llm

# 3) 准备数据（事实表）
#    将 report_agent.db 放到 data/processed/ 下，或用 ETL 脚本重新生成

# 4) 启动服务
python -m uvicorn app.backend.main:app --host 0.0.0.0 --port 8000
```

访问 `http://<服务器IP>:8000`，默认账号 `demo / demo1234`（生产请立即改密）。

## 三、验证清单

| 检查 | 命令 | 期望 |
|---|---|---|
| 健康检查 | `curl http://127.0.0.1:8000/api/health` | `{"status":"ok"}` |
| 首页 | 浏览器打开根路径 | 登录页正常 |
| 核心流程 | 登录 → 生成报告 → 确认 → 导出 | 全链路通过 |

## 四、Nginx + HTTPS 反向代理（生产推荐）

系统本身为 HTTP 服务，生产环境建议前置 Nginx 提供 HTTPS 与静态加速：

```nginx
server {
    listen 443 ssl;
    server_name report.example.com;

    ssl_certificate     /etc/nginx/ssl/report.crt;
    ssl_certificate_key /etc/nginx/ssl/report.key;
    ssl_protocols       TLSv1.2 TLSv1.3;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;      # 大模型解析较慢时留足超时
    }
}
```

> 自签证书（测试环境）：`openssl req -x509 -newkey rsa:2048 -nodes -keyout report.key -out report.crt -days 365 -subj "/CN=report.example.com"`

## 五、安全加固建议（对应任务书 6.2）

1. **传输加密**：如上启用 HTTPS；关闭 8000 端口的外网直接暴露。
2. **密钥管理**：`.env` 权限设为 600，不纳入版本库；API Key 定期轮换。
3. **数据库保护**：`app.db` / `report_agent.db` 限制文件访问权限；敏感环境可用 SQLCipher 加密。
4. **账号安全**：修改种子账号密码，`APP_SECRET_KEY` 改为高强度随机值。
5. **服务常驻**：使用 systemd 或 supervisor 托管进程，配置自动重启。

```ini
# /etc/systemd/system/report-agent.service（示例）
[Unit]
Description=Report Agent
After=network.target
[Service]
WorkingDirectory=/opt/report_agent/backend
ExecStart=/opt/report_agent/backend/.venv/bin/python -m uvicorn app.backend.main:app --host 0.0.0.0 --port 8000
Restart=always
[Install]
WantedBy=multi-user.target
```

## 六、备份与升级

| 对象 | 方式 |
|---|---|
| 应用库 `app.db` | 直接复制文件（发版前备份） |
| 事实表 `report_agent.db` | 可由原始数据 + ETL 重建，一般无需备份 |
| 升级 | 替换 `backend/` 代码与 `static/` 产物 → 重启服务 |
