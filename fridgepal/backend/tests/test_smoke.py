"""冒烟测试：健康检查 + 设备注册 + 语音录入/扣减/查询全链路。

说明：
- 必须在导入 app 之前设置 DATABASE_URL，保证用独立测试库。
- 用 `with TestClient(app)` 触发 lifespan（建表）。
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_fridgepal.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

TEST_USER = "test-user-001"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_device_register(client):
    r = client.post("/api/v1/device/register", json={
        "device_sn": "SN-TEST-001", "device_type": "base",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["device_id"]
    assert data["device_token"]

    # 幂等：重复注册返回同一个 token
    r2 = client.post("/api/v1/device/register", json={
        "device_sn": "SN-TEST-001", "device_type": "base",
    })
    assert r2.json()["device_token"] == data["device_token"]


def test_voice_add_inventory(client):
    r = client.post("/api/v1/ai/chat", json={
        "user_id": TEST_USER,
        "channel": "voice",
        "text": "放了两盒牛奶、一袋鸡蛋大概30个、一块五花肉",
    })
    assert r.status_code == 200
    body = r.json()
    assert "已记录" in body["reply_text"]
    assert len(body["actions"]) == 3

    # 查询确认
    r2 = client.get("/api/v1/inventory", params={"user_id": TEST_USER})
    items = r2.json()
    names = {i["item_name"] for i in items}
    assert {"牛奶", "鸡蛋", "五花肉"} <= names
    milk = next(i for i in items if i["item_name"] == "牛奶")
    assert milk["quantity"] == 2.0
    assert milk["category"] == "dairy"


def test_voice_query(client):
    r = client.post("/api/v1/ai/chat", json={
        "user_id": TEST_USER, "channel": "voice", "text": "鸡蛋还有几个",
    })
    assert r.status_code == 200
    assert "鸡蛋" in r.json()["reply_text"]


def test_voice_consume(client):
    r = client.post("/api/v1/ai/chat", json={
        "user_id": TEST_USER, "channel": "voice", "text": "牛奶喝完了",
    })
    assert r.status_code == 200
    assert "已扣减" in r.json()["reply_text"]

    r2 = client.get("/api/v1/inventory", params={"user_id": TEST_USER, "status": "consumed"})
    consumed = [i for i in r2.json() if i["item_name"] == "牛奶"]
    assert consumed, "牛奶应被标记为已用完"


def test_shopping_list(client):
    r = client.post("/api/v1/ai/chat", json={
        "user_id": TEST_USER, "channel": "voice", "text": "要买酱油和纸巾",
    })
    assert r.status_code == 200
    assert "购物清单" in r.json()["reply_text"]

    r2 = client.get("/api/v1/shopping", params={"user_id": TEST_USER})
    names = {i["item_name"] for i in r2.json()}
    assert {"酱油", "纸巾"} <= names
