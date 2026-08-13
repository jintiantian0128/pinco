#!/usr/bin/env python3
"""Verify the public conversational agent with a disposable persisted user."""

import json
import sys
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8090").rstrip("/")


def call(path, method="GET", body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Pinco-Session"] = token
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


device_id = f"public-agent-smoke-{uuid.uuid4().hex}"
user_id = None
token = None

try:
    status, bootstrap = call(
        "/api/v1/miniapp/bootstrap",
        "POST",
        {"device_id": device_id, "platform": "public-agent-smoke", "nickname": "自动化验收"},
    )
    assert status == 200, (status, bootstrap)
    user_id = bootstrap["user"]["user_id"]
    token = bootstrap["session_token"]

    profile_message = (
        "这是我的长期求职档案，请记住三项信息：工作年限是3年，"
        "目标岗位是AI产品经理，目标城市是上海。只确认你理解了什么，不要记录求职进度。"
    )
    first_status, first = call(
        "/api/v1/chat",
        "POST",
        {"user_id": user_id, "scenario": "career", "messages": [{"role": "user", "content": profile_message}]},
        token,
    )
    assert first_status == 200, (first_status, first)
    assert first.get("agent", {}).get("memory_updated") is True, first
    assert first.get("progress_suggestion") is None, first

    export_status, exported = call(f"/api/v1/account/export?user_id={user_id}", token=token)
    assert export_status == 200, (export_status, exported)
    remembered = exported.get("career_memory") or {}
    assert {"years_experience", "target_role", "target_city"}.issubset(remembered), remembered

    follow_up = "结合你已经知道的我的背景，给我一段面试自我介绍；开头明确工作年限、目标岗位和城市，不要再问我这些信息。"
    second_status, second = call(
        "/api/v1/chat",
        "POST",
        {"user_id": user_id, "scenario": "interview", "messages": [{"role": "user", "content": follow_up}]},
        token,
    )
    assert second_status == 200, (second_status, second)
    answer = second.get("response", "")
    compact_answer = answer.replace(" ", "")
    assert ("3年" in compact_answer or "三年" in compact_answer), answer
    assert "AI产品经理" in compact_answer, answer
    assert "上海" in compact_answer, answer
    used_memory = set(second.get("agent", {}).get("used_memory_keys") or [])
    assert used_memory.intersection({"years_experience", "target_role", "target_city", "career_memory"}), second
    assert second.get("progress_suggestion") is None, second

    reload_status, reloaded = call(
        "/api/v1/miniapp/bootstrap",
        "POST",
        {"device_id": device_id, "platform": "public-agent-smoke", "nickname": "自动化验收"},
    )
    assert reload_status == 200, (reload_status, reloaded)
    persisted_messages = reloaded.get("messages") or []
    assert any(item.get("content") == profile_message for item in persisted_messages), persisted_messages
    assert any(item.get("content") == follow_up for item in persisted_messages), persisted_messages

    print("Public agent smoke passed: real_model=200 server_history=restored career_memory=reused progress_prompt=absent")
finally:
    if user_id and token:
        delete_status, _ = call(
            "/api/v1/account",
            "DELETE",
            {"user_id": user_id, "confirmation": "DELETE"},
            token,
        )
        if delete_status not in {200, 401, 404}:
            raise RuntimeError(f"Disposable account cleanup failed with HTTP {delete_status}")
