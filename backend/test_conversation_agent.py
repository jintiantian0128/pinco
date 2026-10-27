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
    def test_community_author_choice_uses_generated_alias_or_user_supplied_nickname(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            user = main.ensure_user(state, "community-author-device", "微信资料昵称", "weapp")
            user_id = user["profile"]["user_id"]
            store.save(state)
            with patch.object(main, "_state_store", store):
                anonymous = main.create_community_post(main.CommunityPostCreateRequest(
                    user_id=user_id, title="匿名帖子", content="匿名内容", post_type="help",
                    author_mode="anonymous",
                ))["post"]
                public = main.create_community_post(main.CommunityPostCreateRequest(
                    user_id=user_id, title="公开帖子", content="公开内容", post_type="share",
                    author_mode="nickname", display_name="小明同学",
                ))["post"]

        self.assertRegex(anonymous["author"], r"^求职者-[A-F0-9]{4}$")
        self.assertEqual(anonymous["authorMode"], "anonymous")
        self.assertEqual(public["author"], "小明同学")
        self.assertEqual(public["authorMode"], "nickname")

    def test_admin_booking_list_is_token_protected_and_keeps_contact_consent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            state["expert_bookings"] = [{
                "id": "booking-new",
                "created_at": "2026-10-10T10:00:00",
                "user_id": "private-user-id",
                "expert_owner_user_id": "private-expert-id",
                "candidate_alias": "匿名求职者 ABCD",
                "share_contact_with_expert": False,
                "contact_wechat": "should-not-leak",
                "status_code": "intent_submitted",
            }]
            store.save(state)
            with patch.object(main, "_state_store", store), patch.object(main, "PINCO_ADMIN_TOKEN", "admin-test-token"):
                with self.assertRaises(main.HTTPException) as denied:
                    main.list_admin_expert_bookings(None)
                result = main.list_admin_expert_bookings("admin-test-token")

        self.assertEqual(denied.exception.status_code, 403)
        self.assertEqual(len(result["bookings"]), 1)
        self.assertNotIn("user_id", result["bookings"][0])
        self.assertNotIn("contact_wechat", result["bookings"][0])

    def test_failed_client_turn_is_synced_without_transient_error_and_can_be_edited(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            user = main.ensure_user(state, "chat-recovery-device", "小程", "weapp")
            user_id = user["profile"]["user_id"]
            user["messages"] = [
                {"id": "u-ok", "role": "user", "content": "我做过AI客服项目", "createdAt": "10:00"},
                {"id": "a-ok", "role": "assistant", "content": "我们继续拆这个项目。", "createdAt": "10:01"},
            ]
            store.save(state)
            client = [
                main.Message(id="u-ok", role="user", content="我做过AI客服项目"),
                main.Message(id="a-ok", role="assistant", content="我们继续拆这个项目。"),
                main.Message(id="u-failed", role="user", content="负责知识库召回和评估"),
                main.Message(id="temporary-error", role="assistant", content="模型断开，请稍后", transient=True),
                main.Message(id="u-continue", role="user", content="继续帮我完善"),
            ]

            with patch.object(main, "_state_store", store):
                context = main.sync_client_chat_history(user_id, client)
                saved = store.load()["users"][user_id]["messages"]
                self.assertTrue(any(item["id"] == "u-failed" for item in saved))
                self.assertFalse(any("模型断开" in item.get("content", "") for item in saved))
                self.assertTrue(any("负责知识库召回" in item["content"] for item in context))

                edited_client = [client[0], client[1], main.Message(
                    id="u-failed", role="user", content="负责知识库召回，并搭建离线评估集"
                )]
                edited_context = main.sync_client_chat_history(user_id, edited_client, "u-failed")

            saved = store.load()["users"][user_id]["messages"]
            self.assertEqual([item["id"] for item in saved], ["u-ok", "a-ok", "u-failed"])
            self.assertEqual(saved[-1]["content"], "负责知识库召回，并搭建离线评估集")
            self.assertIn("搭建离线评估集", edited_context[-1]["content"])

    def test_new_conversation_does_not_inherit_old_chat_or_job_search_task(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            user = main.ensure_user(state, "chat-isolation-device", "小程", "weapp")
            user_id = user["profile"]["user_id"]
            user["messages"] = [
                {"id": "old-u", "role": "user", "content": "帮我找AI产品经理岗位", "createdAt": "10:00"},
                {"id": "old-a", "role": "assistant", "content": "请补充工作城市。", "createdAt": "10:01"},
            ]
            user["active_agent_task"] = {"type": "job_search", "role": "AI产品经理", "city": "", "missing": ["工作城市或‘不限’"]}
            store.save(state)
            fresh_client = [main.Message(id="new-u", role="user", content="请回答：2+2等于几？只回复数字。")]

            with patch.object(main, "_state_store", store):
                context = main.sync_client_chat_history(user_id, fresh_client)
                saved = store.load()["users"][user_id]

            self.assertEqual(context, [{"role": "user", "content": "请回答：2+2等于几？只回复数字。"}])
            self.assertNotIn("active_agent_task", saved)
            self.assertEqual(len(saved["messages"]), 3)

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

    def test_job_search_accepts_unlimited_city_as_an_explicit_answer(self):
        user = {"career_profile": {"target_roles": [], "cities": [], "years_experience": 0}}
        task = main.resolve_job_search_task(
            {**user, "active_agent_task": {"type": "job_search", "role": "AI产品经理", "city": "", "years": ""}},
            "城市不限",
            None,
        )
        self.assertEqual(task["city"], "不限")
        self.assertEqual(task["missing"], [])

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
                            messages=[main.Message(id="search-start", role="user", content="帮我找一些岗位")],
                        )))
                        self.assertFalse(search_mock.called)
                        self.assertIn("目标岗位", first.response)
                        self.assertIsNotNone(store.load()["users"][user_id].get("active_agent_task"))

                        second = asyncio.run(main.chat(main.ChatRequest(
                            user_id=user_id,
                            messages=[
                                main.Message(id="search-start", role="user", content="帮我找一些岗位"),
                                main.Message(role="assistant", content=first.response),
                                main.Message(id="search-followup", role="user", content="AI产品经理，上海，3年经验"),
                            ],
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

    def test_agent_uses_resume_memory_without_leaking_prior_chat_and_deduplicates_progress(self):
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

            self.assertFalse(any("三年产品经验" in item["content"] for item in captured["messages"]))
            self.assertTrue(any("继续帮我优化项目经历" in item["content"] for item in captured["messages"]))
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

    def test_conversation_profile_keeps_confirmed_facts_and_assumptions_separate(self):
        updated, question = main.apply_conversation_profile_update(
            None,
            {
                "need_type": "job_selection",
                "confirmed_facts": [{"field": "years_of_experience", "value": "2年", "confidence": 0.95}],
                "assumptions": [{"field": "target_role", "value": "AI产品运营"}],
                "ask_field": "target_role",
            },
            "我做了2年运营，但不知道想做什么岗位",
        )
        self.assertEqual(updated["fields"]["years_of_experience"]["status"], "confirmed")
        self.assertEqual(updated["fields"]["target_role"]["status"], "assumption")
        self.assertEqual(updated["confirmed_facts"], ["years_of_experience: 2年"])
        self.assertEqual(updated["assumptions"], ["target_role: AI产品运营"])
        self.assertIsNone(question)

    def test_clarification_is_single_bounded_and_does_not_repeat_declined_field(self):
        profile = main.default_conversation_profile()
        profile["need_type"] = "interview_prep"
        profile["fields"]["need_type"] = {"value": "interview_prep", "status": "inferred"}
        profile, question = main.apply_conversation_profile_update(
            profile, {"need_type": "interview_prep", "ask_field": "target_role"}, "帮我准备面试"
        )
        self.assertEqual(question, main.CLARIFICATION_QUESTIONS["target_role"])
        self.assertEqual(profile["clarification_turns"], 1)

        profile, repeated = main.apply_conversation_profile_update(
            profile, {"need_type": "interview_prep", "ask_field": "target_role"}, "不知道"
        )
        self.assertIsNone(repeated)
        self.assertIsNone(profile["pending_field"])

        profile = main.default_conversation_profile()
        profile["need_type"] = "interview_prep"
        profile["clarification_turns"] = 3
        capped, question = main.apply_conversation_profile_update(
            profile, {"need_type": "interview_prep", "ask_field": "interview_round"}, "准备面试"
        )
        self.assertIsNone(question)
        self.assertEqual(capped["clarification_turns"], 3)

        profile = main.default_conversation_profile()
        profile["need_type"] = "interview_prep"
        profile["pending_field"] = "interview_round"
        profile["asked_fields"] = ["interview_round"]
        declined, question = main.apply_conversation_profile_update(
            profile, {"need_type": "interview_prep", "ask_field": "interview_round"}, "这项不方便说"
        )
        self.assertIsNone(question)
        self.assertIn("interview_round", declined["user_declined_to_answer"])

    def test_conflicting_explicit_profile_value_is_not_silently_overwritten(self):
        profile = main.default_conversation_profile()
        profile["need_type"] = "job_selection"
        profile["fields"]["target_role"] = {"value": "AI产品经理", "status": "confirmed"}
        updated, question = main.apply_conversation_profile_update(
            profile,
            {
                "need_type": "job_selection",
                "confirmed_facts": [{"field": "target_role", "value": "AI产品运营", "confidence": 0.96}],
            },
            "我现在想找AI产品运营",
        )
        self.assertEqual(updated["fields"]["target_role"]["value"], "AI产品经理")
        self.assertEqual(updated["open_questions"][0]["reason"], "conflict")
        self.assertIn("这次应该以哪个为准", question)

    def test_long_conversation_summary_is_saved_only_after_eight_turns(self):
        early, _ = main.apply_conversation_profile_update(
            None, {"need_type": "career_planning", "summary": "太早"}, "继续", turn_count=7
        )
        self.assertEqual(early["summary"], "")
        due, _ = main.apply_conversation_profile_update(
            early, {"need_type": "career_planning", "summary": "确认的事实和待办"}, "继续", turn_count=8
        )
        self.assertEqual(due["summary"], "确认的事实和待办")
        self.assertEqual(due["last_summary_turn"], 8)

    def test_sensitive_questions_are_not_allowlisted_and_question_sentences_can_be_removed(self):
        update = main.normalize_conversation_profile_update({
            "need_type": "job_selection",
            "ask_field": "age",
            "confirmed_facts": [{"field": "age", "value": "28", "confidence": 0.99}],
        })
        self.assertEqual(update["ask_field"], "")
        self.assertEqual(update["confirmed_facts"], [])
        self.assertEqual(main._strip_question_sentences("你多大？先看你做过的项目，再判断可迁移能力。"), "先看你做过的项目，再判断可迁移能力。")

    def test_conversation_profile_fields_can_be_forgotten(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            user = main.ensure_user(state, "profile-forget-device", "用户", "weapp")
            user_id = user["profile"]["user_id"]
            user["conversation_profile"] = {
                **main.default_conversation_profile(),
                "fields": {"current_status": {"value": "在职", "status": "confirmed"}},
                "confirmed_facts": ["current_status: 在职"],
            }
            store.save(state)
            with patch.object(main, "_state_store", store):
                result = main.forget_career_memory(main.CareerMemoryForgetRequest(
                    user_id=user_id, key="current_status"
                ))
            self.assertTrue(result["removed"])
            self.assertNotIn("current_status", result["conversation_profile"]["fields"])
            self.assertEqual(result["conversation_profile"]["confirmed_facts"], [])

    def test_chat_persists_profile_update_and_backend_question_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            user = main.ensure_user(state, "profile-loop-device", "小程", "weapp")
            user_id = user["profile"]["user_id"]
            store.save(state)

            def fake_llm(_messages, **_kwargs):
                return json.dumps({
                    "response": "你有运营经验，可以先从相邻岗位盘点可迁移能力。请问你想找哪类岗位？另外几年经验？",
                    "intent": "job_selection",
                    "next_action": "确认目标岗位",
                    "used_memory_keys": [],
                    "memory_updates": [],
                    "profile_update": {
                        "need_type": "job_selection",
                        "confirmed_facts": [{"field": "years_of_experience", "value": "2年", "confidence": 0.95}],
                        "assumptions": [],
                        "user_declined_to_answer": [],
                        "ask_field": "target_role",
                        "summary": "",
                    },
                    "progress_suggestion": None,
                }, ensure_ascii=False)

            with patch.object(main, "_state_store", store), patch.object(main, "llm_chat_with_fallback", side_effect=fake_llm):
                response = asyncio.run(main.chat(main.ChatRequest(
                    user_id=user_id,
                    messages=[main.Message(id="profile-loop-u1", role="user", content="我有2年运营经验，帮我想想转什么岗位")],
                )))
            saved = store.load()["users"][user_id]["conversation_profile"]
            self.assertEqual(saved["fields"]["years_of_experience"]["value"], "2年")
            self.assertEqual(saved["fields"]["years_of_experience"]["status"], "confirmed")
            self.assertEqual(saved["pending_field"], "target_role")
            self.assertEqual(response.response.count("？") + response.response.count("?"), 1)
            self.assertIn("为了给你更贴合的建议", response.response)


if __name__ == "__main__":
    unittest.main()
