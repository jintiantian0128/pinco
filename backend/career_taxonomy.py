"""Curated AI-career role taxonomy adapted from Pinco's 2025 legacy prototype.

The legacy repository contained useful role aliases and preparation dimensions,
but also stale scraped jobs, fixed mock results, and unsupported platform APIs.
Only stable taxonomic assets live here. They improve retrieval and planning; they
must never be presented as current hiring facts or verified company interview data.
"""

from typing import Any, Dict, List


ROLE_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "ai_product_manager": {
        "label": "AI 产品经理",
        "aliases": [
            "AI产品经理", "人工智能产品经理", "智能产品经理", "大模型产品经理",
            "算法产品经理", "机器学习产品经理", "AI产品", "Agent产品经理",
        ],
        "search_terms": ["AI product manager", "LLM product manager", "AI platform product manager"],
        "focus": [
            "用户问题与业务价值", "模型能力边界与方案取舍", "数据和评测指标",
            "产品实验与复盘", "跨团队推动", "成本、时延与 ROI",
        ],
    },
    "ai_product_operations": {
        "label": "AI 产品运营",
        "aliases": ["AI产品运营", "AI运营", "大模型运营", "智能产品运营", "AI增长运营"],
        "search_terms": ["AI product operations", "AI growth operations", "LLM product operations"],
        "focus": [
            "用户分层与场景运营", "内容和增长策略", "漏斗指标与实验设计",
            "AI 产品教育", "留存与活跃复盘", "跨产品和销售协同",
        ],
    },
    "ai_algorithm_engineer": {
        "label": "AI 算法工程师",
        "aliases": [
            "AI算法工程师", "算法工程师", "机器学习工程师", "深度学习工程师",
            "NLP工程师", "自然语言处理工程师", "推荐算法工程师", "大模型算法工程师",
        ],
        "search_terms": ["machine learning engineer", "LLM engineer", "NLP engineer"],
        "focus": [
            "算法与数据结构", "机器学习基础", "模型评测与误差分析",
            "训练和推理工程", "系统设计与性能权衡", "项目业务价值与复盘",
        ],
    },
    "ai_application_engineer": {
        "label": "AI 应用工程师",
        "aliases": ["AI应用工程师", "大模型应用工程师", "Agent工程师", "AI全栈工程师"],
        "search_terms": ["AI application engineer", "LLM application engineer", "AI agent engineer"],
        "focus": [
            "RAG 与知识检索", "Agent 工具调用与状态管理", "评测与可观测性",
            "安全和权限边界", "成本与时延优化", "端到端交付",
        ],
    },
}


def match_role_track(text: str) -> str:
    normalized = "".join(str(text or "").lower().split())
    if not normalized:
        return ""
    matches = []
    for track, config in ROLE_TAXONOMY.items():
        aliases = [str(item) for item in config["aliases"]]
        score = max((len(alias) for alias in aliases if "".join(alias.lower().split()) in normalized), default=0)
        if score:
            matches.append((score, track))
    return max(matches)[1] if matches else ""


def translate_job_query(query: str) -> str:
    track = match_role_track(query)
    if not track:
        return query
    return str(ROLE_TAXONOMY[track]["search_terms"][0])


def role_interview_focus(position: str) -> List[str]:
    track = match_role_track(position)
    return list(ROLE_TAXONOMY[track]["focus"]) if track else []
