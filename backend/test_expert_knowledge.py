import json
import os
import tempfile
import unittest
from unittest.mock import patch

import main
from expert_knowledge import EXPERT_KNOWLEDGE_VERSION, build_expert_knowledge_context
from state_store import JsonFileStateStore


class ExpertKnowledgeTests(unittest.TestCase):
    def test_retrieval_is_versioned_and_model_agnostic(self):
        context, cards = build_expert_knowledge_context(
            "DeepSeek 基座以后可能更换，如何设计模型路由、成本和迁移预案？",
            target_role="AI 产品经理",
        )

        self.assertIn(EXPERT_KNOWLEDGE_VERSION, context)
        self.assertIn("model_strategy", cards)
        self.assertIn("unit_economics", cards)
        self.assertNotIn("用户做过", context)

    def test_draft_is_not_memory_until_user_confirms(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonFileStateStore(os.path.join(directory, "state.json"), main.default_beta_state)
            state = main.default_beta_state()
            user = main.ensure_user(state, "evidence-draft-device", "证据用户", "weapp")
            user_id = user["profile"]["user_id"]
            store.save(state)
            model_result = {
                "draft": {
                    "title": "AI 助手首次任务改版",
                    "situation": "新用户完成首次任务的路径过长",
                    "action": "访谈用户并把首次任务从五步调整为三步",
                    "result": "次周留存提升，具体口径待确认",
                    "metrics": "访谈 12 位用户",
                    "skills": ["问题发现与产品判断", "Agent 系统编排"],
                    "confidence_questions": ["留存提升的统计口径是什么？"],
                },
                "resume_bullet": "通过用户访谈重构 AI 助手首次任务路径。",
                "role_directions": [
                    {
                        "role": "AI 产品经理",
                        "fit": "high",
                        "reason": "已有用户研究和产品取舍证据",
                        "existing_evidence": "访谈并重构首次任务",
                        "largest_gap": "补充留存口径",
                        "search_query": "AI 产品经理 Agent",
                    },
                    {
                        "role": "AI 产品运营",
                        "fit": "explore",
                        "reason": "可探索用户激活方向",
                        "existing_evidence": "有新用户路径优化经验",
                        "largest_gap": "缺运营实验案例",
                        "search_query": "AI 产品运营 用户增长",
                    },
                ],
            }

            with patch.object(main, "_state_store", store), patch.object(
                main, "llm_chat_with_fallback", return_value=json.dumps(model_result, ensure_ascii=False)
            ):
                response = main.draft_career_evidence(main.EvidenceDraftRequest(
                    user_id=user_id,
                    narrative="我访谈了十二位用户，把 AI 助手首次任务从五步改成三步，留存后来有提升。",
                    include_resume_memory=False,
                    target_role="AI 产品经理",
                ))

            self.assertEqual(store.load()["users"][user_id].get("evidence", []), [])
            self.assertIn("尚未写入", response["source_boundary"])
            self.assertEqual(response["expert_knowledge"]["version"], EXPERT_KNOWLEDGE_VERSION)

            with patch.object(main, "_state_store", store):
                saved = main.create_evidence(main.EvidenceCreateRequest(
                    user_id=user_id,
                    title=response["draft"]["title"],
                    situation=response["draft"]["situation"],
                    action=response["draft"]["action"],
                    result=response["draft"]["result"],
                    metrics=response["draft"]["metrics"],
                    skills=response["draft"]["skills"],
                ))["evidence"]

            persisted_user = store.load()["users"][user_id]
            self.assertEqual(persisted_user["evidence"][0]["id"], saved["id"])
            self.assertIn("confirmed_evidence", main.build_agent_memory_context(persisted_user))
            self.assertIn("AI 助手首次任务改版", main.build_agent_memory_context(persisted_user))
            radar = main.build_capability_radar(persisted_user)
            self.assertEqual(radar["competency_version"], EXPERT_KNOWLEDGE_VERSION)
            self.assertEqual(len(radar["dimensions"]), 8)


if __name__ == "__main__":
    unittest.main()
