"""后端接口测试：鉴权、报告生成（同步模式）、确认回写、归档、历史列表。

运行：从项目根目录 `python -m pytest app/backend/test_api.py -q`
生成采用 ?sync=true，保证测试确定性（返回即已完成）。
"""
import pytest
from fastapi.testclient import TestClient

from app.backend.main import app
from app.backend.db import SessionLocal, init_db
from app.backend.models import Report, User

init_db()

# 每次测试前清空应用状态表，避免相互污染
@pytest.fixture(autouse=True)
def _reset():
    db = SessionLocal()
    try:
        db.query(Report).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    # 注册并登录一个新用户，返回带 Bearer 的请求头
    r = client.post("/api/auth/register", json={"username": "alice", "password": "secret123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_register_and_login(client):
    r = client.post("/api/auth/register", json={"username": "bob", "password": "pw123456"})
    assert r.status_code == 200 and "access_token" in r.json()
    # 重复注册应被拒
    assert client.post("/api/auth/register", json={"username": "bob", "password": "pw123456"}).status_code == 400
    # 错误密码登录应被拒
    bad = client.post("/api/auth/login", json={"username": "bob", "password": "wrong"})
    assert bad.status_code == 401
    ok = client.post("/api/auth/login", json={"username": "bob", "password": "pw123456"})
    assert ok.status_code == 200


def test_generate_requires_auth(client):
    r = client.post("/api/reports/generate", params={"sync": True}, json={"instruction": "昨日日报"})
    assert r.status_code == 401


def test_full_report_lifecycle(client, auth_headers):
    # 1) 生成（同步）
    r = client.post(
        "/api/reports/generate",
        params={"sync": True},
        json={"instruction": "生成昨日日报"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    rid = body["id"]
    assert body["status"] == "drafted"
    assert body["markdown"] and "GMV" in body["markdown"]
    assert body["metrics_json"]

    # 2) 预览
    g = client.get(f"/api/reports/{rid}", headers=auth_headers)
    assert g.status_code == 200 and g.json()["id"] == rid

    # 3) 确认回写（drafted -> confirmed，版本+1）
    c = client.post(f"/api/reports/{rid}/confirm", headers=auth_headers)
    assert c.status_code == 200, c.text
    cj = c.json()
    assert cj["status"] == "confirmed"
    assert cj["version"] == 2
    assert cj["confirmed_at"]

    # 4) 归档
    a = client.post(f"/api/reports/{rid}/archive", headers=auth_headers)
    assert a.status_code == 200 and a.json()["status"] == "archived"

    # 5) 历史列表可见
    lst = client.get("/api/reports", headers=auth_headers)
    assert lst.status_code == 200 and any(x["id"] == rid for x in lst.json())


def test_confirm_only_from_drafted(client, auth_headers):
    r = client.post(
        "/api/reports/generate", params={"sync": True},
        json={"instruction": "上周全市场周报"}, headers=auth_headers,
    )
    rid = r.json()["id"]
    # 直接归档未确认应为 400（状态为 drafted，允许；改为确认前先测非法：先确认再确认应 400）
    assert client.post(f"/api/reports/{rid}/confirm", headers=auth_headers).status_code == 200
    assert client.post(f"/api/reports/{rid}/confirm", headers=auth_headers).status_code == 400


def test_cannot_access_others_report(client, auth_headers):
    r = client.post(
        "/api/reports/generate", params={"sync": True},
        json={"instruction": "本月月报"}, headers=auth_headers,
    )
    rid = r.json()["id"]
    # 另一个用户
    other = client.post("/api/auth/register", json={"username": "eve", "password": "pw123456"}).json()["access_token"]
    oh = {"Authorization": f"Bearer {other}"}
    assert client.get(f"/api/reports/{rid}", headers=oh).status_code == 404
