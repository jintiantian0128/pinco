#!/usr/bin/env python3
"""Exercise the user session boundary over real HTTP without printing secrets."""

import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8090"


def call(path, method="GET", body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Pinco-Session"] = token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


status, bootstrap = call(
    "/api/v1/miniapp/bootstrap",
    "POST",
    {"device_id": "smoke-session-device", "platform": "http-smoke", "nickname": "自动化验收"},
)
assert status == 200, (status, bootstrap)
health_status, health = call("/health")
assert health_status == 200 and health["version"] == "0.7.0", (health_status, health)
user_id = bootstrap["user"]["user_id"]
token = bootstrap["session_token"]
assert token and "session_token_hash" not in bootstrap["user"]

unauthorized_status, _ = call(f"/api/v1/workspace?user_id={user_id}")
assert unauthorized_status == 401, unauthorized_status

authorized_status, workspace = call(f"/api/v1/workspace?user_id={user_id}", token=token)
assert authorized_status == 200 and "jobs" in workspace

plans_status, plans = call(f"/api/v1/membership/plans?user_id={user_id}", token=token)
assert plans_status == 200 and not any(item["purchasable"] for item in plans["plans"])
payment_status, payment_error = call(
    "/api/v1/membership/subscribe",
    "POST",
    {
        "user_id": user_id,
        "plan_id": "pro",
        "billing_cycle": "monthly",
        "request_id": "smoke-payment-disabled-001",
    },
    token,
)
assert payment_status == 503 and payment_error["detail"]["code"] == "PAYMENT_NOT_AVAILABLE"

post_status, created = call(
    "/api/v1/community/posts",
    "POST",
    {
        "user_id": user_id,
        "title": "自动化会话边界验收",
        "content": "这是一条写入隔离测试状态文件的自动化验收记录。",
        "post_type": "share",
    },
    token,
)
assert post_status == 200 and created["post"]["title"] == "自动化会话边界验收"

export_status, exported = call(f"/api/v1/account/export?user_id={user_id}", token=token)
assert export_status == 200 and "session_token_hash" not in exported["profile"]

delete_status, deleted = call(
    "/api/v1/account",
    "DELETE",
    {"user_id": user_id, "confirmation": "DELETE"},
    token,
)
assert delete_status == 200 and deleted["deleted"] is True
after_delete_status, _ = call(f"/api/v1/workspace?user_id={user_id}", token=token)
assert after_delete_status == 401

print("HTTP smoke passed: v0.7.0 session_guard=401/200 payment_fail_closed=503 community_write=200 export/delete=200")
