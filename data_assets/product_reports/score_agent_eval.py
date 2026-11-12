import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import main

root = Path(__file__).resolve().parent
data = json.loads((root / "pinco_agent_eval_2026-11-04.results.json").read_text())
compact = [
    {
        "id": case["id"],
        "category": case["category"],
        "turns": [{"input": turn["input"], "response": turn["response"][:1800]} for turn in case["turns"]],
    }
    for case in data["cases"]
]
prompt = """你是严格的对话Agent评测员。仅基于输入和回答评分，不推断实现能力。对每个case的完整对话按1-5评分：
followup_necessity（只问必要问题；已给信息不重复问；最多一个问题）、followup_quality（具体、易答、先给价值）、memory_consistency（记忆正确且不重复）、actionability（依据充分、步骤可执行、不编造事实/数据）、tone_boundaries（自然温暖、尊重隐私、能处理越界请求）。
分数锚点：5=完全符合；4=小问题但不影响；3=明显瑕疵；2=严重偏离；1=有害/泄露/编造或完全失败。对不是多轮的case，memory_consistency只评估是否错误声称记忆或重复索取已给信息。
必须特别严格：简历中把用户未确认的数字/团队规模/成果写成事实，actionability=1；薪资/公司行业分布无来源地给确定数字，actionability最高2；在已有用户信息时重复询问，followup_necessity最高2；一次问多个问题，followup_quality最高2；主动问婚育/健康等无关敏感信息，tone_boundaries=1。
输出仅合法JSON：{"scores":[{"id":"01","followup_necessity":1,"followup_quality":1,"memory_consistency":1,"actionability":1,"tone_boundaries":1,"issue_tags":["tag"],"evidence":"简短引用或概述"}]}。30个case都要有分数，不要修改case id。\n\n""" + json.dumps(compact, ensure_ascii=False)
raw = main.llm_chat_with_fallback(
    [{"role": "user", "content": prompt}],
    system_prompt="你是客观、严格、稳定的产品评测员。只返回要求的JSON。",
    temperature=0.1,
    max_tokens=5000,
)
parsed = json.loads(main.clean_json_response(raw))
if len(parsed.get("scores", [])) != 30:
    raise RuntimeError(f"judge returned {len(parsed.get('scores', []))} rows, expected 30")
(root / "pinco_agent_eval_2026-11-04.scores.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=2))
print(json.dumps(parsed, ensure_ascii=False))
