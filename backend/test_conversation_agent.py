import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import main
from state_store import JsonFileStateStore


class ConversationAgentTests(unittest.TestCase):
    def test_profile_statement_does_not_trigger_job_search(self):
        message = [{"role": "user", "content": "请记住：我的目标岗位是AI产品经理，目标城市上海"}]
        self.assertIsNone(main.detect_search_intent(message))
        self.assertEqual(
            main.detect_search_intent([{"role": "user", "content": "帮我搜索上海在招的AI产品经理岗位"}]),
            "帮我搜索上海在招的AI产品经理岗位",
        )

    def test_localized_memory_keys_are_normalized(self):
        result = main.sanitize_agent_result({
            "response": "已经记住。",
            "used_memory_keys": ["工作经验", "目标岗位", "所在城市"],
            "memory_updates": [
                {"key": "工作年限", "value": "3年", "confidence": 0.95},
                {"key": "目标岗位", "value": "AI产品经理", "confidence": 0.95},
                {"key": "目标城市", "value": "上海", "confidence": 0.95},
            ],
        })
        self.assertEqual(
            result["used_memory_keys"],
            ["years_experience", "target_role", "target_city"],
        )
        self.assertEqual(
            [item["key"] for item in result["memory_updates"]],
            ["years_experience", "target_role", "target_city"],
        )

    def test_agent_uses_server_history_resume_memory_and_deduplicates_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            user = main.ensure_user(state, "agent-device", "小程", "weapp")
            user_id = user["profile"]["user_id"]
            user["messages"].append({"id": "u-old", "role": "user", "content": "我有三年产品经验", "createdAt": "10:00"})
            user["resume_memory"] = {
                "filename": "resume.pdf",
                "analysis_summary": "有 AI 产品项目经历",
                "text_excerpt": "负责大模型评测产品，推动核心指标提升 30%",
                "updated_at": main.now_iso(),
            }
            store.save(state)
            captured = {}

            def fake_llm(messages, **kwargs):
                captured["messages"] = messages
                captured["system"] = kwargs.get("system_prompt", "")
                return json.dumps({
                    "response": "我会沿用你简历里的大模型评测经历，不再让你重复粘贴。",
                    "intent": "resume_follow_up",
                    "next_action": "完善岗位匹配表达",
                    "used_memory_keys": ["latest_resume"],
                    "memory_updates": [{"key": "target_role", "value": "AI 产品经理", "confidence": 0.96}],
                    "progress_suggestion": {
                        "milestone": "resume_completed",
                        "company": "目标公司",
                        "position": "AI 产品经理",
                        "status": "saved",
                        "prompt": "要顺手记录这版简历对应的岗位吗？",
                    },
                }, ensure_ascii=False)

            request = main.ChatRequest(
                user_id=user_id,
                scenario="resume",
                messages=[main.Message(role="user", content="继续帮我优化项目经历")],
            )
            with patch.object(main, "_state_store", store), patch.object(main, "llm_chat_with_fallback", side_effect=fake_llm):
                first = asyncio.run(main.chat(request))
                second = asyncio.run(main.chat(request))

            self.assertTrue(any("三年产品经验" in item["content"] for item in captured["messages"]))
            self.assertIn("负责大模型评测产品", captured["system"])
            self.assertTrue(first.agent["memory_updated"])
            self.assertIsNotNone(first.progress_suggestion)
            self.assertIsNone(second.progress_suggestion)
            saved_user = store.load()["users"][user_id]
            self.assertEqual(saved_user["career_memory"]["target_role"]["value"], "AI 产品经理")

    def test_memory_allowlist_rejects_sensitive_or_low_confidence_updates(self):
        result = main.sanitize_agent_result({
            "response": "收到。",
            "intent": "profile",
            "next_action": "继续",
            "used_memory_keys": [],
            "memory_updates": [
                {"key": "phone", "value": "13800000000", "confidence": 0.99},
                {"key": "target_city", "value": "上海", "confidence": 0.5},
                {"key": "target_role", "value": "AI 产品运营", "confidence": 0.9},
            ],
            "progress_suggestion": {"milestone": "ordinary_chat", "status": "applied"},
        })
        self.assertEqual(result["memory_updates"], [{"key": "target_role", "value": "AI 产品运营", "confidence": 0.9}])
        self.assertIsNone(result["progress_suggestion"])


if __name__ == "__main__":
    unittest.main()
