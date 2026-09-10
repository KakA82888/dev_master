"""后端真实 HTTP 冒烟测试：覆盖完整报告生命周期 + 安全校验。
使用 httpx 真实发起请求，验证服务在运行态下的行为。
用户名带随机后缀，保证可重复运行（后端 app.db 跨重启持久化）。
"""
import json
import sys
import uuid
import httpx

BASE = "http://127.0.0.1:8000"
SUF = uuid.uuid4().hex[:8]


def main():
    results = []  # (name, actual_code, expect_ok, detail)

    def add(name, code, expect_ok, detail):
        results.append((name, code, expect_ok, detail))

    with httpx.Client(base_url=BASE, timeout=30) as c:
        # 1. health
        r = c.get("/api/health")
        add("health", r.status_code, (200 <= r.status_code < 300), r.json())

        # 2. 未授权访问受保护接口 -> 401
        r = c.post("/api/reports/generate", json={"instruction": "生成昨日日报"})
        add("generate_no_auth(期望401)", r.status_code, (r.status_code == 401), r.text[:80])

        # 3. 注册用户A
        ua = f"smoke_a_{SUF}"
        r = c.post("/api/auth/register", json={"username": ua, "password": "pw123456"})
        add("register A", r.status_code, (200 <= r.status_code < 300 and "access_token" in r.json()),
            "access_token" in r.json())
        tok_a = r.json()["access_token"]
        hA = {"Authorization": f"Bearer {tok_a}"}

        # 4. 重复注册 -> 400
        r = c.post("/api/auth/register", json={"username": ua, "password": "pw123456"})
        add("register dup(期望400)", r.status_code, (r.status_code == 400), r.text[:60])

        # 5. 登录
        r = c.post("/api/auth/login", json={"username": ua, "password": "pw123456"})
        add("login A", r.status_code, (200 <= r.status_code < 300 and "access_token" in r.json()),
            "access_token" in r.json())

        # 6. 生成报告（同步）
        r = c.post("/api/reports/generate",
                   json={"instruction": "生成2011年11月22日的日报"},
                   params={"sync": "true"}, headers=hA)
        add("generate(sync)", r.status_code, (200 <= r.status_code < 300), r.json().get("status"))
        rep = r.json()
        rid = rep["id"]

        # 7. 报告内容检查
        mk = rep.get("markdown") or ""
        mj = rep.get("metrics_json") or ""
        has_gmv = ("GMV" in mk) or ("gmv" in mj.lower())
        add("report_content(GMV非空)", 200 if has_gmv else 0, has_gmv,
            f"len(markdown)={len(mk)}, metrics_len={len(mj)}")

        # 8. 列表
        r = c.get("/api/reports", headers=hA)
        add("list_reports", r.status_code, (200 <= r.status_code < 300), f"count={len(r.json())}")

        # 9. 获取单条
        r = c.get(f"/api/reports/{rid}", headers=hA)
        add("get_report", r.status_code, (200 <= r.status_code < 300 and r.json().get("id") == rid),
            r.json().get("id") == rid)

        # 10. 确认（drafted -> confirmed）
        r = c.post(f"/api/reports/{rid}/confirm", headers=hA)
        add("confirm", r.status_code, (200 <= r.status_code < 300), r.json().get("status"))

        # 11. 再次确认应失败（400）
        r = c.post(f"/api/reports/{rid}/confirm", headers=hA)
        add("confirm_again(期望400)", r.status_code, (r.status_code == 400), r.text[:60])

        # 12. 导出 markdown
        r = c.get(f"/api/reports/{rid}/export", params={"fmt": "md"}, headers=hA)
        add("export_md", r.status_code, (200 <= r.status_code < 300),
            r.headers.get("content-type", "")[:30])

        # 13. 导出 docx
        r = c.get(f"/api/reports/{rid}/export", params={"fmt": "docx"}, headers=hA)
        add("export_docx", r.status_code, (200 <= r.status_code < 300),
            r.headers.get("content-type", "")[:30])

        # 14. 用户B 越权访问A的报告 -> 404
        ub = f"smoke_b_{SUF}"
        r = c.post("/api/auth/register", json={"username": ub, "password": "pw123456"})
        tok_b = r.json()["access_token"]
        hB = {"Authorization": f"Bearer {tok_b}"}
        r = c.get(f"/api/reports/{rid}", headers=hB)
        add("cross_user_get(期望404)", r.status_code, (r.status_code == 404), r.text[:60])

        # 15. B 未授权导出A的报告 -> 404
        r = c.get(f"/api/reports/{rid}/export", params={"fmt": "md"}, headers=hB)
        add("cross_user_export(期望404)", r.status_code, (r.status_code == 404), r.text[:60])

    print("=== 后端 HTTP 冒烟测试结果 ===")
    ok = 0
    for name, code, expect_ok, detail in results:
        mark = "✅" if expect_ok else "❌"
        if expect_ok:
            ok += 1
        print(f"  {mark} {name}: HTTP {code} | {detail}")
    print(f"\n通过 {ok}/{len(results)} 项")
    return ok == len(results)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
