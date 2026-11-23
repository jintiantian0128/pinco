import asyncio
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main
from state_store import JsonFileStateStore


class AgenticWorkflowTests(unittest.TestCase):
    def test_agentic_task_intent_cases(self):
        cases = [
            ("按我的背景推荐岗位并给出投递优先级", "job_recommendation"),
            ("根据我的背景推荐岗位", "job_recommendation"),
            ("推荐岗位并排序", "job_recommendation"),
            ("给出投递优先级", "job_recommendation"),
            ("推荐适合我的岗位", "job_recommendation"),
            ("针对这个JD改简历", "jd_resume"),
            ("按这个JD改简历", "jd_resume"),
            ("根据JD优化简历", "jd_resume"),
            ("针对JD优化简历", "jd_resume"),
            ("优化简历匹配JD", "jd_resume"),
            ("帮我随便聊聊求职", None),
            ("我在想简历怎么写", None),
        ]
        for utterance, expected in cases:
            with self.subTest(utterance=utterance):
                self.assertEqual(main.detect_agentic_task_request(utterance), expected)

    def test_job_candidate_validation_eval_cases(self):
        for candidate, city, expected in self._job_candidate_cases():
            with self.subTest(candidate=candidate):
                self.assertEqual(bool(main._validate_job_candidates([candidate] if isinstance(candidate, dict) else [candidate], city)), expected)

    def test_resume_grounding_eval_cases(self):
        for bullet, evidence, expected in self._resume_grounding_cases():
            with self.subTest(bullet=bullet):
                verified = main._verify_resume_draft({"resume_bullets": [bullet]}, evidence)
                self.assertEqual(bool(verified["resume_bullets"]), expected)

    def test_old_uploaded_resume_can_ground_drafts_without_evidence_card(self):
        user = {"resume_memory": {
            "filename": "old-resume.pdf",
            "text_excerpt": "负责搭建智能客服知识库召回，推动转化率提升18%。",
        }}
        source = main._agent_task_source_evidence(user)
        self.assertEqual(source[0]["id"], "resume-memory-latest")
        self.assertEqual(source[0]["source_type"], "uploaded_resume_unconfirmed")
        verified = main._verify_resume_draft(
            {"resume_bullets": [{"text": "搭建智能客服知识库召回，转化率提升18%", "evidence_ids": ["resume-memory-latest"]}]},
            source,
        )
        self.assertEqual(len(verified["resume_bullets"]), 1)
        self.assertEqual(main._agent_task_source_evidence({}), [])

    def test_job_task_requires_confirmation_then_persists_each_step(self):
        async def fake_search(_request):
            return SimpleNamespace(jobs=[main.JobResult(
                title="AI产品经理", company="甲公司", location="上海", summary="AI产品与知识库",
                url="https://jobs.example/ai-pm", source="招聘来源", verified_source=True,
            )], query_analysis={"status": "source_linked_candidates"})

        plan = {"steps": [{"id": item["id"], "title": item["title"], "tool": item["tool"], "expected_output": item["expected_output"]} for item in main.AGENTIC_TASK_PLANS["job_recommendation"]]}
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            user = main.ensure_user(state, "agentic-job-device", "求职者", "weapp")
            user_id = user["profile"]["user_id"]
            user["career_profile"] = {"target_roles": ["AI产品经理"], "cities": ["上海"], "years_experience": 2, "strengths": ["知识库"]}
            store.save(state)
            messages = [main.Message(id="request", role="user", content="按我的背景推荐岗位并给出投递优先级")]
            with patch.object(main, "_state_store", store), patch.object(main, "llm_chat_with_fallback", return_value=json.dumps(plan, ensure_ascii=False)), patch.object(main, "search_jobs", side_effect=fake_search):
                planned = asyncio.run(main.chat(main.ChatRequest(user_id=user_id, messages=messages)))
                saved = store.load()["users"][user_id]
                self.assertEqual(saved["agent_tasks"][0]["status"], "awaiting_confirmation")
                self.assertIn("确认开始", planned.response)
                self.assertFalse(any(step["status"] == "completed" for step in saved["agent_tasks"][0]["steps"]))

                approved_messages = messages + [
                    main.Message(role="assistant", content=planned.response),
                    main.Message(id="confirm", role="user", content="确认开始"),
                ]
                completed = asyncio.run(main.chat(main.ChatRequest(user_id=user_id, messages=approved_messages)))

            saved_task = store.load()["users"][user_id]["agent_tasks"][0]
            self.assertEqual(saved_task["status"], "completed")
            self.assertTrue(all(step["status"] == "completed" for step in saved_task["steps"]))
            self.assertIn("jobs.example/ai-pm", completed.response)
            self.assertIn("来源页确认", completed.response)

    def test_invalid_model_plan_is_reported_as_fixed_recovery_plan(self):
        invalid = {"steps": [
            {"id": "context", "title": "读取画像", "tool": "read_everything", "expected_output": "画像"},
            {"id": "search", "title": "搜索", "tool": "search_jobs", "expected_output": "候选"},
            {"id": "verify", "title": "校验", "tool": "verify_jobs", "expected_output": "结果"},
        ]}
        with patch.object(main, "llm_chat_with_fallback", return_value=json.dumps(invalid, ensure_ascii=False)):
            plan, source = main._agent_task_plan_with_source("job_recommendation", {}, "推荐岗位")
        self.assertEqual(source, "fixed_recovery_plan")
        self.assertEqual({step["tool"] for step in plan}, main.AGENT_TASK_TOOLS["job_recommendation"])

    def test_missing_profile_clarifies_one_field_and_does_not_repeat_tool_without_input(self):
        async def fake_search(_request):
            return SimpleNamespace(jobs=[main.JobResult(
                title="AI产品经理", company="甲公司", location="杭州", summary="AI产品与Agent",
                url="https://jobs.example/hz-ai-pm", source="招聘来源", verified_source=True,
            )], query_analysis={"status": "source_linked_candidates"})

        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            user = main.ensure_user(state, "agentic-clarification-device", "求职者", "weapp")
            user_id = user["profile"]["user_id"]
            user["agent_tasks"] = [{
                "id": "task-clarify", "type": "job_recommendation", "title": "岗位推荐与投递优先级",
                "status": "awaiting_input", "inputs": {"role": "", "city": ""}, "outputs": {},
                "missing_inputs": ["目标岗位", "目标城市或‘不限’"], "next_input": "target_role",
                "steps": [
                    {**step, "status": "failed" if step["id"] == "context" else "pending", "attempts": 1 if step["id"] == "context" else 0}
                    for step in main.AGENTIC_TASK_PLANS["job_recommendation"]
                ],
                "failure": {"code": "MISSING_PROFILE", "message": "需要补充信息"},
            }]
            store.save(state)
            initial_messages = [main.Message(id="resume-task", role="user", content="继续任务")]
            with patch.object(main, "_state_store", store), patch.object(main, "search_jobs", side_effect=fake_search):
                clarification = asyncio.run(main.chat(main.ChatRequest(user_id=user_id, messages=initial_messages)))
                saved = store.load()["users"][user_id]["agent_tasks"][0]
                self.assertEqual(saved["steps"][0]["attempts"], 1)
                self.assertIn("哪类岗位", clarification.response)

                role_messages = initial_messages + [
                    main.Message(role="assistant", content=clarification.response),
                    main.Message(id="role-answer", role="user", content="AI产品经理"),
                ]
                city_question = asyncio.run(main.chat(main.ChatRequest(user_id=user_id, messages=role_messages)))
                saved = store.load()["users"][user_id]["agent_tasks"][0]
                self.assertEqual(saved["inputs"]["role"], "AI产品经理")
                self.assertEqual(saved["status"], "awaiting_input")
                self.assertIn("哪个城市", city_question.response)

                city_messages = role_messages + [
                    main.Message(role="assistant", content=city_question.response),
                    main.Message(id="city-answer", role="user", content="杭州"),
                ]
                completed = asyncio.run(main.chat(main.ChatRequest(user_id=user_id, messages=city_messages)))
            saved = store.load()["users"][user_id]["agent_tasks"][0]
        self.assertEqual(saved["status"], "completed")
        self.assertIn("杭州", completed.response, json.dumps(saved, ensure_ascii=False))

    def test_jd_resume_task_runs_plan_grounding_and_user_review_end_to_end(self):
        plan_json = json.dumps({"steps": [
            {"id": step["id"], "title": step["title"], "tool": step["tool"], "expected_output": step["expected_output"]}
            for step in main.AGENTIC_TASK_PLANS["jd_resume"]
        ]}, ensure_ascii=False)
        draft_json = json.dumps({
            "jd_requirements": ["知识库召回优化"],
            "gaps": ["尚未提供项目结果数字"],
            "resume_bullets": [{"text": "搭建智能客服知识库召回并优化流程", "evidence_ids": ["ev-grounded"]}],
        }, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            user = main.ensure_user(state, "agentic-jd-device", "求职者", "weapp")
            user_id = user["profile"]["user_id"]
            user["evidence"] = [{
                "id": "ev-grounded", "title": "智能客服项目", "situation": "客服知识查找效率低",
                "action": "搭建智能客服知识库召回并优化流程", "result": "检索流程可用",
                "metrics": "", "skills": ["知识库召回"],
            }]
            store.save(state)
            messages = [main.Message(id="jd-task", role="user", content="针对这个JD改简历：负责知识库召回优化和客服效率提升")]
            with patch.object(main, "_state_store", store), patch.object(main, "llm_chat_with_fallback", side_effect=[plan_json, draft_json]):
                planned = asyncio.run(main.chat(main.ChatRequest(user_id=user_id, messages=messages)))
                self.assertIn("确认开始", planned.response)
                approved = messages + [
                    main.Message(role="assistant", content=planned.response),
                    main.Message(id="confirm-jd", role="user", content="确认开始"),
                ]
                finished = asyncio.run(main.chat(main.ChatRequest(user_id=user_id, messages=approved)))
                task = store.load()["users"][user_id]["agent_tasks"][0]
        self.assertEqual(task["status"], "completed")
        self.assertTrue(all(step["status"] == "completed" for step in task["steps"]))
        self.assertIn("搭建智能客服知识库召回", finished.response)
        self.assertIn("不会自动覆盖简历", finished.response)

    def test_benchmark_case_counts_meet_planned_minimum(self):
        # Existing deterministic case tables: 15 job-source/city cases and 12
        # resume-evidence grounding cases, matching the 10–15 case plan.
        self.assertEqual(len(self._job_candidate_cases()), 15)
        self.assertEqual(len(self._resume_grounding_cases()), 12)

    @staticmethod
    def _job_candidate_cases():
        base = {"title": "AI产品经理", "company": "甲公司", "location": "上海", "summary": "AI产品职位", "url": "https://jobs.example/1", "verified_source": True}
        return [
            (base, "上海", True), ({**base, "title": ""}, "上海", False),
            ({**base, "company": ""}, "上海", False), ({**base, "location": ""}, "上海", False),
            ({**base, "summary": ""}, "上海", False), ({**base, "url": ""}, "上海", False),
            ({**base, "url": "javascript:alert(1)"}, "上海", False), ({**base, "verified_source": False}, "上海", False),
            ({**base, "location": "北京"}, "上海", False), ({**base, "location": "上海/远程"}, "上海", True),
            ({**base, "location": "北京"}, "不限", True), ({**base, "location": "上海"}, "远程", False),
            ({**base, "location": "远程"}, "远程", True), ({**base, "company": "未知公司"}, "上海", False),
            ("not-a-job", "上海", False),
        ]

    @staticmethod
    def _resume_grounding_cases():
        evidence = [{
            "id": "ev-1", "title": "智能客服项目", "situation": "客服问题多",
            "action": "搭建知识库召回并优化流程", "result": "转化率提升18%",
            "metrics": "18%", "skills": ["知识库", "评估"],
        }]
        return [(bullet, evidence, expected) for bullet, expected in [
            ({"text": "搭建知识库召回并优化流程", "evidence_ids": ["ev-1"]}, True),
            ({"text": "转化率提升18%", "evidence_ids": ["ev-1"]}, True),
            ({"text": "转化率提升28%", "evidence_ids": ["ev-1"]}, False),
            ({"text": "主导团队完成项目", "evidence_ids": []}, False),
            ({"text": "主导团队完成项目", "evidence_ids": ["missing"]}, False),
            ({"text": "", "evidence_ids": ["ev-1"]}, False),
            ({"text": "使用知识库", "evidence_ids": ["ev-1", "missing"]}, True),
            ({"text": "转化率提升18.0%", "evidence_ids": ["ev-1"]}, False),
            ({"text": "转化率提升18%并降低成本30%", "evidence_ids": ["ev-1"]}, False),
            ({"text": "优化客服流程", "evidence_ids": ["ev-1"]}, True),
            ({"text": "使用 Python 构建系统", "evidence_ids": ["ev-1"]}, False),
            ({"text": "实现 18% 增长", "evidence_ids": ["ev-1"]}, False),
        ]]

    def test_revised_task_keeps_unaffected_completed_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            user = main.ensure_user(state, "agentic-revision-device", "求职者", "weapp")
            user_id = user["profile"]["user_id"]
            user["career_profile"] = {"target_roles": ["AI产品经理"], "cities": ["上海"], "years_experience": 2, "strengths": []}
            user["agent_tasks"] = [{
                "id": "task-existing", "type": "job_recommendation", "title": "岗位推荐",
                "status": "failed", "inputs": {"role": "AI产品经理", "city": "上海"},
                "outputs": {"context": {"role": "AI产品经理", "city": "上海"}},
                "steps": [
                    {"id": "context", "title": "读取画像", "tool": "load_profile", "expected_output": "画像", "status": "completed", "attempts": 1},
                    {"id": "search", "title": "搜索", "tool": "search_jobs", "expected_output": "候选", "status": "failed", "attempts": 1},
                    {"id": "rank", "title": "排序", "tool": "rank_jobs", "expected_output": "顺序", "status": "pending", "attempts": 0},
                    {"id": "verify", "title": "校验", "tool": "verify_jobs", "expected_output": "清单", "status": "pending", "attempts": 0},
                ],
            }]
            store.save(state)
            messages = [
                main.Message(role="assistant", content="计划失败，已保存进度。"),
                main.Message(id="revision", role="user", content="把城市改成杭州"),
            ]
            with patch.object(main, "_state_store", store):
                response = asyncio.run(main.chat(main.ChatRequest(user_id=user_id, messages=messages)))
                revised = store.load()["users"][user_id]["agent_tasks"][0]

        self.assertIn("确认开始", response.response)
        self.assertEqual(revised["id"], "task-existing")
        self.assertEqual(revised["inputs"]["city"], "杭州")
        statuses = {step["id"]: step["status"] for step in revised["steps"]}
        self.assertEqual(statuses["context"], "completed")
        self.assertEqual(statuses["search"], "pending")
        self.assertIn("context", revised["outputs"])
        self.assertNotIn("search", revised["outputs"])

    def test_admin_metrics_are_aggregated_without_returning_task_content(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            user = main.ensure_user(state, "agentic-metric-device", "求职者", "weapp")
            user["agent_tasks"] = [{
                "id": "task-secret", "type": "jd_resume", "status": "completed",
                "inputs": {"jd_text": "private job description"}, "retry_count": 1,
                "steps": [{"id": "verify", "status": "completed", "attempts": 2}],
                "outputs": {"verify": {"rejected_suggestions": [{"text": "private resume"}]}},
            }]
            store.save(state)
            with patch.object(main, "_state_store", store), patch.object(main, "PINCO_ADMIN_TOKEN", "admin-token-that-is-longer-than-32-chars"):
                metrics = main.get_agent_task_metrics("admin-token-that-is-longer-than-32-chars")
        self.assertEqual(metrics["task_count"], 1)
        self.assertEqual(metrics["completion_rate"], 1.0)
        self.assertEqual(metrics["retry_rate"], 1.0)
        self.assertEqual(metrics["verification_intercept_task_rate"], 1.0)
        self.assertNotIn("private job description", json.dumps(metrics))
        self.assertNotIn("private resume", json.dumps(metrics))


if __name__ == "__main__":
    unittest.main()
