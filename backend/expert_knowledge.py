"""Versioned, model-agnostic expert knowledge for Pinco's AI career agent.

This module is deliberately separate from user memory:

* Expert knowledge is reviewed product methodology shared by all users.
* User memory contains only user-confirmed career facts and preferences.
* The base model is a replaceable reasoning engine; prompts receive only the
  small set of knowledge cards relevant to the current decision.

The first release is a conservative distillation of
``最新AI产品经理认知体系_ 前沿AI信息持续深度沉淀.md``. The source document
states that parts may be AI-generated, so time-sensitive company/market claims
are intentionally excluded from production guidance.
"""

from typing import Any, Dict, List, Tuple
import re


EXPERT_KNOWLEDGE_VERSION = "ai-pm-2026.09-v1"


AI_PRODUCT_COMPETENCY_MODEL: List[Dict[str, Any]] = [
    {
        "key": "problem_judgment",
        "label": "问题发现与产品判断",
        "definition": "先判断什么问题值得用 AI 解决、为谁解决、成功长什么样，再讨论功能和模型。",
        "evidence_signals": ["真实用户摩擦", "非 AI 方案比较", "成功指标", "主动取舍或砍功能"],
        "probe_questions": ["你为什么判断这是值得解决的问题？", "不用 AI 时最好的替代方案是什么？"],
        "anti_patterns": ["从模型能力倒推伪需求", "把功能清单当产品判断"],
        "keywords": ["需求", "用户", "问题", "场景", "产品判断", "优先级", "pmf", "取舍"],
    },
    {
        "key": "agent_orchestration",
        "label": "Agent 系统编排",
        "definition": "把智能任务拆成 Brain、Hands、Session 以及可检查的规划、执行、验证循环。",
        "evidence_signals": ["任务拆解", "工具边界", "状态/记忆设计", "验证器", "失败恢复"],
        "probe_questions": ["模型负责判断什么，确定性系统负责执行什么？", "每一步如何知道做对和做完？"],
        "anti_patterns": ["只会写 Prompt", "用一个超长上下文包办所有任务", "没有停止与恢复条件"],
        "keywords": ["agent", "智能体", "编排", "brain", "hands", "session", "工作流", "工具调用", "规划"],
    },
    {
        "key": "context_memory",
        "label": "上下文与记忆工程",
        "definition": "设计 Agent 每次决策时看见、记住、压缩、隔离和遗忘什么，而不是只优化单条提示词。",
        "evidence_signals": ["上下文分层", "长期/短期记忆", "检索策略", "冲突与过期处理", "用户可见可删"],
        "probe_questions": ["哪些信息必须跨会话保留？", "错误或过期记忆怎样被发现和撤销？"],
        "anti_patterns": ["把聊天全文永久塞入上下文", "把用户事实和公共知识混存", "无授权推断敏感信息"],
        "keywords": ["上下文", "记忆", "memory", "检索", "知识库", "rag", "个性化", "跨会话"],
    },
    {
        "key": "evaluation_reliability",
        "label": "评测与可靠性",
        "definition": "把验收定义权产品化，分别评估一致性、鲁棒性、可预测性和安全性，并检查完整任务轨迹。",
        "evidence_signals": ["离线集与线上指标", "失败样本分类", "轨迹评测", "逐维门槛", "回归机制"],
        "probe_questions": ["什么证据证明它可靠，而不只是偶尔答对？", "最差的失败案例如何归因和回流？"],
        "anti_patterns": ["只看单一准确率", "只展示最佳 Demo", "用综合分掩盖安全尾部风险"],
        "keywords": ["评测", "eval", "可靠性", "准确率", "幻觉", "测试", "失败", "指标", "鲁棒"],
    },
    {
        "key": "model_strategy",
        "label": "模型判断与可替换架构",
        "definition": "按质量、延迟、成本、敏感度和可定制性选择够用模型，用抽象层避免单一供应商绑定。",
        "evidence_signals": ["模型基准", "路由策略", "降级边界", "迁移预案", "任务级成本"],
        "probe_questions": ["为什么这个任务需要这个模型？", "明天更换基座时哪些资产可以原样保留？"],
        "anti_patterns": ["排行榜最高即选型", "把模型独占当长期壁垒", "模型失败后用假答案兜底"],
        "keywords": ["模型", "基座", "deepseek", "路由", "成本", "延迟", "供应商", "选型", "多模型"],
    },
    {
        "key": "trust_risk",
        "label": "信任、风险与人类问责",
        "definition": "能力越强越要分级授权、可解释、可撤销和可审计；AI 可以建议与执行，人类保留问责。",
        "evidence_signals": ["权限梯度", "人工确认点", "审计日志", "撤销/回滚", "风险分级"],
        "probe_questions": ["最坏情况下谁承担后果？", "哪些动作必须由人确认才能继续？"],
        "anti_patterns": ["能力上线后再补安全", "把 AI 建议悄悄变成 AI 决策", "越权读取或执行"],
        "keywords": ["信任", "风险", "安全", "权限", "合规", "隐私", "治理", "审核", "负责"],
    },
    {
        "key": "unit_economics",
        "label": "Token 与单位经济学",
        "definition": "用户为结果价值付费；模型性能达到任务门槛后，继续堆能力必须由单位成本和收益证明。",
        "evidence_signals": ["单任务成本", "价值/成本比", "Token 预算", "缓存或路由优化", "毛利红线"],
        "probe_questions": ["完成一次用户结果的真实成本是多少？", "贵模型多出的质量是否改变业务结果？"],
        "anti_patterns": ["只算调用价格不算重试和人工兜底", "忽略高频长链路的复合成本"],
        "keywords": ["token", "成本", "毛利", "roi", "预算", "价格", "付费", "经济性"],
    },
    {
        "key": "production_delivery",
        "label": "从 Demo 到可交付结果",
        "definition": "完成不是模型给出答案，而是价值抵达现实并留下可核验产物；生产竞争发生在模型周围的运行系统。",
        "evidence_signals": ["端到端完成率", "真实环境验证", "可核验产物", "可观测性", "异常恢复"],
        "probe_questions": ["用户最后拿到了什么现实结果？", "离开演示环境后最容易在哪一步失败？"],
        "anti_patterns": ["接口通了就宣布完成", "用 Demo 质量代表生产可靠性"],
        "keywords": ["上线", "交付", "生产", "demo", "部署", "完成率", "可观测", "结果"],
    },
    {
        "key": "human_agency",
        "label": "用户理解权与思维主权",
        "definition": "AI 应放大用户而不是替用户失去判断；关键决策要让用户看懂理由、提出自己的假设并能够接管。",
        "evidence_signals": ["理由可见", "不确定性标注", "用户修改", "人工接管", "先假设后 AI"],
        "probe_questions": ["用户用了以后是更懂还是更依赖？", "系统如何让用户纠正它的判断？"],
        "anti_patterns": ["只给结论不展示依据", "把用户变成照读 AI 的话筒"],
        "keywords": ["解释", "理解", "接管", "自主", "选择", "修改", "透明", "为什么"],
    },
    {
        "key": "vertical_moat",
        "label": "窄域工作流与能力飞轮",
        "definition": "基础模型能力会商品化，长期壁垒来自专有数据、深度工作流、用户习惯、反馈和生态整合。",
        "evidence_signals": ["窄域闭环", "使用反馈回流", "专有数据权", "跨环节状态", "复用与留存"],
        "probe_questions": ["不用更强模型，系统为什么仍会越用越好？", "哪个工作流状态是通用聊天工具没有的？"],
        "anti_patterns": ["用更多功能掩盖工作流不深", "依赖单个模型版本形成壁垒"],
        "keywords": ["壁垒", "护城河", "垂直", "窄域", "数据", "生态", "留存", "工作流", "反馈"],
    },
]


def _normalized_tokens(text: str) -> List[str]:
    lowered = str(text or "").lower()
    return re.findall(r"[a-z0-9+#.-]+|[\u4e00-\u9fff]{2,}", lowered)


def select_expert_knowledge(query: str, target_role: str = "", limit: int = 4) -> List[Dict[str, Any]]:
    """Return a small, deterministic set of relevant reviewed cards."""
    text = f"{query} {target_role}".lower()
    tokens = _normalized_tokens(text)
    ai_product_role = any(value in text for value in ["ai产品", "ai 产品", "产品经理", "agent 产品"])
    default_ai_product_keys = {
        "problem_judgment", "agent_orchestration", "evaluation_reliability", "production_delivery",
    }
    scored: List[Tuple[int, int, Dict[str, Any]]] = []
    for index, card in enumerate(AI_PRODUCT_COMPETENCY_MODEL):
        score = 0
        for keyword in card["keywords"]:
            normalized = keyword.lower()
            if normalized in text:
                score += 4 if len(normalized) > 2 else 2
            elif normalized in tokens:
                score += 2
        if ai_product_role and card["key"] in default_ai_product_keys:
            score += 1
        scored.append((score, -index, card))
    selected = [item[2] for item in sorted(scored, reverse=True) if item[0] > 0][:limit]
    if not selected and any(value in text for value in ["ai产品", "产品经理", "agent", "大模型"]):
        selected = [AI_PRODUCT_COMPETENCY_MODEL[index] for index in [0, 1, 3, 7]][:limit]
    return selected


def build_expert_knowledge_context(query: str, target_role: str = "", limit: int = 4) -> Tuple[str, List[str]]:
    cards = select_expert_knowledge(query, target_role, limit=limit)
    if not cards:
        return "", []
    lines = [
        f"【Pinco AI 产品专家知识 · {EXPERT_KNOWLEDGE_VERSION}】",
        "以下是经产品侧审核的共享方法论，不是该用户的个人记忆。只在相关时使用，不得声称用户具备未提供的能力。",
    ]
    for card in cards:
        lines.extend([
            f"- {card['label']}：{card['definition']}",
            f"  可验证信号：{'、'.join(card['evidence_signals'])}",
            f"  优先追问：{'；'.join(card['probe_questions'])}",
            f"  避免误区：{'、'.join(card['anti_patterns'])}",
        ])
    return "\n".join(lines), [card["key"] for card in cards]


def ai_product_direction_summary() -> Dict[str, Any]:
    return {
        "role": "AI 产品经理",
        "competency_version": EXPERT_KNOWLEDGE_VERSION,
        "dimensions": [card["label"] for card in AI_PRODUCT_COMPETENCY_MODEL],
    }
