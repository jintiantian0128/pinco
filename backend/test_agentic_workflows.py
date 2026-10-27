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
        base = {"title": "AI产品经理", "company": "甲公司", "location": "上海", "summary": "AI产品职位", "url": "https://jobs.example/1", "verified_source": True}
        cases = [
            (base, "上海", True),
            ({**base, "title": ""}, "上海", False),
            ({**base, "company": ""}, "上海", False),
            ({**base, "location": ""}, "上海", False),
            ({**base, "summary": ""}, "上海", False),
            ({**base, "url": ""}, "上海", False),
            ({**base, "url": "javascript:alert(1)"}, "上海", False),
            ({**base, "verified_source": False}, "上海", False),
            ({**base, "location": "北京"}, "上海", False),
            ({**base, "location": "上海/远程"}, "上海", True),
            ({**base, "location": "北京"}, "不限", True),
            ({**base, "location": "上海"}, "远程", False),
            ({**base, "location": "远程"}, "远程", True),
            ({**base, "company": "未知公司"}, "上海", False),
            ("not-a-job", "上海", False),
        ]
        for candidate, city, expected in cases:
            with self.subTest(candidate=candidate):
                self.assertEqual(bool(main._validate_job_candidates([candidate] if isinstance(candidate, dict) else [candidate], city)), expected)

    def test_resume_grounding_eval_cases(self):
        evidence = [{
            "id": "ev-1", "title": "智能客服项目", "situation": "客服问题多",
            "action": "搭建知识库召回并优化流程", "result": "转化率提升18%",
            "metrics": "18%", "skills": ["知识库", "评估"],
        }]
        cases = [
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
        ]
        for bullet, expected in cases:
            with self.subTest(bullet=bullet):
                verified = main._verify_resume_draft({"resume_bullets": [bullet]}, evidence)
                self.assertEqual(bool(verified["resume_bullets"]), expected)

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
