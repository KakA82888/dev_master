# 实训附录 部署与 Nginx HTTPS 配置

## 一、实训目标

1. 掌握前后端分离应用的两种部署方式（单端口托管 / Nginx 网关分离）
2. 学会申请与生成 SSL 证书，配置 HTTPS 服务
3. 理解反向代理的常见配置项（超时、请求头、静态资源）
4. 能够把服务注册为系统服务（systemd）实现常驻与自动重启
5. 掌握生产环境安全加固要点

## 二、实训内容

### 1. 背景知识

- **单端口部署**：后端直接托管前端构建产物（`backend/static/`），只暴露一个端口，配置最简单。
- **Nginx 反向代理**：由 Nginx 统一对外提供 80/443，转发 API 请求到后端，同时托管静态资源、配置 SSL。
- **SSL/TLS**：HTTPS 的加密基础；测试可用自签证书，生产建议使用受信任 CA 签发的证书。
- **systemd**：Linux 服务管理器，可实现开机自启、崩溃自动重启、日志集中管理。

### 2. 项目结构

```
部署版code/report_agent/
└── backend/
    ├── app/               FastAPI 源码
    ├── static/            前端构建产物（已内置）
    ├── requirements.txt
    └── .env.example
```

## 三、实训步骤

### 步骤1：单端口部署并验证

**操作：**

```bash
cd 部署版code/report_agent/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# 生产必改：APP_SECRET_KEY、SEED_PASSWORD

python -m uvicorn app.backend.main:app --host 0.0.0.0 --port 8000
```

**操作结果：**
- 服务启动，访问 `http://<服务器IP>:8000` 即为完整应用（前端已内置）。

**操作验证：**
- `curl http://127.0.0.1:8000/api/health` → `{"status":"ok"}`；
- 浏览器打开首页，登录 `demo / demo1234` 并走通一次报告生成。

> 【截图位】建议插入：服务启动成功截图

**操作说明：**

1. **为什么部署版不需要 Node.js？**
   前端已在开发阶段构建为静态文件并内置，服务器只需运行后端。

2. **端口选择**
   演示可用 8000；生产建议由 Nginx 暴露 443，后端只监听内网。

### 步骤2：配置 Nginx HTTPS 反向代理

**操作：**

1. 安装 Nginx（以 OpenEuler/CentOS 为例）：

```bash
yum install -y nginx
systemctl enable nginx
```

2. 生成自签证书（测试环境）：

```bash
mkdir -p /etc/nginx/ssl
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout /etc/nginx/ssl/report.key \
  -out /etc/nginx/ssl/report.crt \
  -days 365 -subj "/CN=report.example.com"
```

3. 编写配置 `/etc/nginx/conf.d/report.conf`：

```nginx
server {
    listen 443 ssl;
    server_name report.example.com;

    ssl_certificate     /etc/nginx/ssl/report.crt;
    ssl_certificate_key /etc/nginx/ssl/report.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;   # 大模型解析较慢，超时要留足
    }
}

server {
    listen 80;
    server_name report.example.com;
    return 301 https://$host$request_uri;   # HTTP 自动跳转 HTTPS
}
```

4. 检查并重载：

```bash
nginx -t
systemctl reload nginx
```

**操作结果：**
- 通过 `https://report.example.com` 可访问系统，HTTP 自动跳转 HTTPS。

**操作验证：**
- 浏览器地址栏显示锁标志，证书信息可查看；
- 登录并生成一份报告，确认代理转发正常（尤其是长耗时请求不超时）。

> 【截图位】建议插入：HTTPS 访问成功截图

**操作说明：**

1. **`proxy_read_timeout` 为什么重要？**
   启用大模型通道后单次生成可能数十秒，Nginx 默认 60s 超时会导致前端报错。必须放大到 180s 以上。

2. **自签证书的提示**
   浏览器会提示"证书不受信任"，测试环境可忽略；生产应使用受信任 CA 签发的证书。

### 步骤3（可选）：多端口 / 前后端分离部署

**操作：**

若前端单独部署（如 5173/静态服务器），后端仅提供 API，则需配置跨域或统一网关：

```nginx
# 前端静态站点
server {
    listen 443 ssl;
    server_name report.example.com;
    root /opt/report_agent/frontend/dist;
    index index.html;

    location / { try_files $uri $uri/ /index.html; }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_read_timeout 180s;
    }
}
```

**操作说明：**

- 单端口方案（步骤1+2）配置更少、无跨域问题，**推荐优先使用**；
- 分离部署适合前端需要独立 CDN 加速的场景，但需处理 CORS 或统一网关。

### 步骤4：注册为系统服务（常驻运行）

**操作：**

```ini
# /etc/systemd/system/report-agent.service
[Unit]
Description=Report Agent Service
After=network.target

[Service]
WorkingDirectory=/opt/report_agent/backend
ExecStart=/opt/report_agent/backend/.venv/bin/python -m uvicorn app.backend.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now report-agent
systemctl status report-agent
```

**操作验证：**
- 重启服务器后服务自动运行；
- 手动 kill 进程后 3 秒内自动重启。

## 四、注意事项

1. **安全加固**：修改默认账号密码与 `APP_SECRET_KEY`；限制数据库文件权限；不对外暴露后端端口。

2. **超时配置**：涉及大模型的接口必须放大 Nginx 与后端超时，否则长任务会被中断。

3. **日志与排查**：Nginx 错误日志 `/var/log/nginx/error.log`；后端日志用 `journalctl -u report-agent -f` 查看。

4. **备份**：定期备份应用库 `app.db`；事实表可由原始数据重建。

5. **实训管理**：部署完成后务必按《部署检查清单》逐项打勾，并留档验证截图。
