# Nginx_HTTPS服务配置语料库

**主题：** Nginx 安装、SSL 证书、HTTPS 服务与反向代理配置
**适用范围：** 运维人员、部署人员、学习者
**版本：** v1.0

---

## Q: 为什么生产环境要用 Nginx 前置？

**A:** 三个理由：
1. **HTTPS 终止**：由 Nginx 处理 TLS 加解密，后端只需提供 HTTP 服务，配置更简单
2. **静态资源加速**：Nginx 托管静态文件的性能远优于应用服务器
3. **安全与可控**：统一入口便于配置限流、访问日志、来源限制，且后端端口不必对外暴露

**标签：** Nginx, 反向代理, HTTPS终止, 架构设计

---

## Q: 如何在 Linux 上安装 Nginx？

**A:**

```bash
# OpenEuler / CentOS / RHEL
yum install -y nginx
systemctl enable nginx
systemctl start nginx

# Ubuntu / Debian
apt update && apt install -y nginx
systemctl enable --now nginx

# 验证
nginx -v
curl -I http://127.0.0.1
```

**标签：** Nginx安装, 系统服务, 安装步骤, 实操

---

## Q: 如何生成自签名 SSL 证书（测试环境）？

**A:**

```bash
mkdir -p /etc/nginx/ssl
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout /etc/nginx/ssl/report.key \
  -out /etc/nginx/ssl/report.crt \
  -days 365 \
  -subj "/CN=report.example.com"
```

- `-nodes`：私钥不加密（便于服务自动读取）
- `-days 365`：有效期一年
- `-subj`：证书主体信息（CN 应为访问域名）

浏览器会提示"证书不受信任"，测试环境可忽略；生产应使用受信任 CA 签发的证书。

**标签：** SSL证书, 自签证书, openssl, 实操

---

## Q: 如何配置 HTTPS 反向代理？

**A:** 创建 `/etc/nginx/conf.d/report.conf`：

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
        proxy_read_timeout 180s;
    }
}

server {
    listen 80;
    server_name report.example.com;
    return 301 https://$host$request_uri;
}
```

```bash
nginx -t && systemctl reload nginx
```

**标签：** HTTPS配置, 反向代理, server块, 实操

---

## Q: `proxy_read_timeout` 为什么必须调大？

**A:** 因为启用大模型通道后，单次报告生成可能耗时数十秒。Nginx 默认读取超时为 60 秒，超时会导致前端收到 504 错误。本项目建议设置为 180 秒以上，与后端处理时长匹配。

**标签：** 超时配置, proxy_read_timeout, 504错误, 性能配置

---

## Q: 前后端分离部署时 Nginx 怎么配？

**A:** 由 Nginx 同时托管前端静态文件并把 `/api` 转发给后端：

```nginx
server {
    listen 443 ssl;
    server_name report.example.com;

    ssl_certificate     /etc/nginx/ssl/report.crt;
    ssl_certificate_key /etc/nginx/ssl/report.key;

    root /opt/report_agent/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;   # 支持前端路由
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_read_timeout 180s;
    }
}
```

注意：单端口方案（后端托管前端）配置更简单且无跨域问题，**优先推荐**；分离部署适合前端需要独立 CDN 的场景。

**标签：** 前后端分离, 静态托管, try_files, 实操

---

## Q: 如何配置多端口（多个后端实例）负载均衡？

**A:** 当需要多实例部署时，用 upstream 定义后端池：

```nginx
upstream report_backend {
    server 127.0.0.1:8001 weight=1;
    server 127.0.0.1:8002 weight=1;
    # 会话粘性（如需）
    ip_hash;
}

server {
    listen 443 ssl;
    server_name report.example.com;

    ssl_certificate     /etc/nginx/ssl/report.crt;
    ssl_certificate_key /etc/nginx/ssl/report.key;

    location / {
        proxy_pass http://report_backend;
        proxy_set_header Host $host;
        proxy_read_timeout 180s;
    }
}
```

注意：本项目的应用库为 SQLite 单文件，多实例同时写入会冲突。若要真正多实例，需先把应用库迁移到支持并发的数据库（如 PostgreSQL/MySQL）。

**标签：** 负载均衡, upstream, 多端口, 实操

---

## Q: HTTPS 配置完成后如何验证？

**A:** 四项检查：
1. `nginx -t` 语法检查通过
2. 浏览器访问 `https://域名` 显示锁标志，证书信息可查看
3. `curl -I https://域名/api/health` 返回 200 与 `{"status":"ok"}`
4. 走通一次完整业务（登录 → 生成 → 确认 → 导出），确认长耗时请求不超时

**标签：** 验证, HTTPS检查, 联调, 实操

---

## Q: HTTPS 相关的常见问题有哪些？

**A:**

| 现象 | 原因 | 处理 |
|---|---|---|
| 浏览器提示证书不受信任 | 使用自签证书 | 测试环境可忽略；生产换受信任 CA 证书 |
| 504 Gateway Timeout | `proxy_read_timeout` 过小 | 调大到 180s 以上 |
| 静态资源 404 | `root` 路径或 `try_files` 配置错误 | 检查 dist 路径与 index.html 是否存在 |
| HTTP 未跳转 HTTPS | 缺少 80 端口跳转 server 块 | 增加 `return 301 https://$host$request_uri` |
| 后端收到的 IP 都是 127.0.0.1 | 未透传请求头 | 配置 `X-Real-IP` / `X-Forwarded-For` |

**标签：** 常见问题, 故障排查, HTTPS, 实操
