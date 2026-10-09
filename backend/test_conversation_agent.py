import asyncio
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main
from state_store import JsonFileStateStore


async def collect_sse(response):
    return [chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk) async for chunk in response.body_iterator]


class ConversationAgentTests(unittest.TestCase):
    def test_career_profile_is_source_of_truth_and_memory_can_be_forgotten(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            user = main.ensure_user(state, "profile-memory-device", "职业用户", "weapp")
            user_id = user["profile"]["user_id"]
            user["career_memory"] = {
                "target_role": {"value": "旧岗位", "confidence": 0.9, "source": "conversation"},
                "current_company": {"value": "示例公司", "confidence": 0.9, "source": "conversation"},
            }
            store.save(state)

            with patch.object(main, "_state_store", store):
                updated = main.update_career_profile(main.CareerProfileRequest(
                    user_id=user_id,
                    target_roles=["AI产品经理"],
                    years_experience=3,
                    cities=["上海"],
                    strengths=["Agent评测"],
                ))
                forgotten = main.forget_career_memory(main.CareerMemoryForgetRequest(
                    user_id=user_id, key="目标岗位"
                ))

            self.assertEqual(updated["career_memory"]["target_role"]["value"], "AI产品经理")
            self.assertEqual(updated["career_memory"]["years_experience"]["value"], "3.0")
            self.assertIn("current_company", updated["career_memory"])
            self.assertTrue(forgotten["removed"])
            self.assertNotIn("target_role", forgotten["career_memory"])
            self.assertEqual(forgotten["career_profile"]["target_roles"], [])
            self.assertNotIn("旧岗位", main.build_agent_memory_context(store.load()["users"][user_id]))

    def test_profile_statement_does_not_trigger_job_search(self):
        message = [{"role": "user", "content": "请记住：我的目标岗位是AI产品经理，目标城市上海"}]
        self.assertIsNone(main.detect_search_intent(message))
        self.assertEqual(
            main.detect_search_intent([{"role": "user", "content": "帮我搜索上海在招的AI产品经理岗位"}]),
            "帮我搜索上海在招的AI产品经理岗位",
        )

    def test_job_search_task_waits_for_missing_inputs_then_continues(self):
        user = {"career_profile": {"target_roles": [], "cities": [], "years_experience": 0}}
        initial = main.resolve_job_search_task(user, "帮我找一些岗位", "帮我找一些岗位")
        self.assertEqual(initial["missing"], ["目标岗位", "工作城市或‘不限’"])
        continued = main.resolve_job_search_task(
            {**user, "active_agent_task": initial},
            "AI产品经理，上海，3年经验",
            None,
        )
        self.assertEqual(continued["role"], "AI产品经理")
        self.assertEqual(continued["city"], "上海")
        self.assertEqual(continued["years"], "3年经验")
        self.assertEqual(continued["missing"], [])

    def test_chat_persists_search_clarification_and_uses_verified_results(self):
        async def fake_search(request):
            captured["search_request"] = request
            return SimpleNamespace(
                jobs=[main.JobResult(
                    title="AI产品经理", company="示例公司", location="上海", summary="来源职位摘要",
                    url="https://example.com/job/1", source="provider", verified_source=True,
                )],
                query_analysis={"query": request.query},
            )

        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            user = main.ensure_user(state, "agent-search-device", "小程", "weapp")
            user_id = user["profile"]["user_id"]
            store.save(state)
            captured = {"llm_calls": 0}

            def fake_llm(messages, **kwargs):
                captured["llm_calls"] += 1
                return json.dumps({
                    "response": "我先确认目标岗位和城市，再开始检索。",
                    "intent": "job_search",
                    "next_action": "补充岗位与城市后继续搜索",
                    "used_memory_keys": [],
                    "memory_updates": [],
                    "progress_suggestion": None,
                }, ensure_ascii=False)

            with patch.object(main, "_state_store", store):
                with patch.object(main, "llm_chat_with_fallback", side_effect=fake_llm):
                    with patch.object(main, "search_jobs", side_effect=fake_search) as search_mock:
                        first = asyncio.run(main.chat(main.ChatRequest(
                            user_id=user_id,
                            messages=[main.Message(role="user", content="帮我找一些岗位")],
                        )))
                        self.assertFalse(search_mock.called)
                        self.assertIn("目标岗位", first.response)
                        self.assertIsNotNone(store.load()["users"][user_id].get("active_agent_task"))

                        second = asyncio.run(main.chat(main.ChatRequest(
                            user_id=user_id,
                            messages=[main.Message(role="user", content="AI产品经理，上海，3年经验")],
                        )))

            self.assertEqual(search_mock.call_count, 1)
            self.assertIn("AI产品经理", captured["search_request"].query)
            self.assertEqual(captured["search_request"].city, "上海")
            self.assertEqual(len(second.search_results or []), 1)
            self.assertIn("example.com/job/1", second.response)
            self.assertNotIn("active_agent_task", store.load()["users"][user_id])

    def test_stream_route_uses_same_agent_and_emits_action_metadata(self):
        expected = main.ChatResponse(
            response="已沿用你的简历记忆。",
            agent={"next_action": "挑选一个目标岗位"},
            progress_suggestion=None,
        )

        async def fake_chat(_request):
            return expected

        with patch.object(main, "chat", side_effect=fake_chat):
            response = asyncio.run(main.chat_stream(main.ChatRequest(
                messages=[main.Message(role="user", content="继续")]
            )))
            events = asyncio.run(collect_sse(response))
        self.assertTrue(any("已沿用你的简历记忆。" in event for event in events))
        self.assertTrue(any('"next_action": "挑选一个目标岗位"' in event for event in events))


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

    def test_used_memory_keys_are_recovered_when_model_omits_metadata(self):
        result = main.sanitize_agent_result({
            "response": "面试官好，我有3年经验，目前在上海，目标是AI产品经理。",
            "used_memory_keys": [],
        })
        user = {
            "career_memory": {
                "years_experience": {"value": "3.0", "confidence": 0.95},
                "target_role": {"value": "AI产品经理", "confidence": 0.95},
                "target_city": {"value": "上海", "confidence": 0.95},
                "current_company": {"value": "未在回答出现的公司", "confidence": 0.95},
            }
        }

        used = main.reconcile_agent_used_memory_keys(result, user, result["response"])

        self.assertEqual(used, ["years_experience", "target_role", "target_city"])
        self.assertNotIn("current_company", used)

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
