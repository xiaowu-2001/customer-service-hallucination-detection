# llm_client.py
import json
import re
import config
import utils
from openai import OpenAI

# 预加载 ground_truth 用于 Mock
_ground_truth = None


def _load_ground_truth():
    global _ground_truth
    if _ground_truth is None:
        _ground_truth = {item["id"]: item for item in utils.load_json(config.GROUND_TRUTH_PATH) or []}
    return _ground_truth


def call_llm(user_question: str, system_reply: str, knowledge_base: str, item_id: str = None):
    """调用 LLM 判断幻觉，支持 Mock 模式和鲁棒解析"""

    # ---------- Mock 模式 ----------
    if config.MOCK_MODE:
        utils.logger.info(f"🔄 [Mock] 使用人工标注作为模拟结果 (id={item_id})")
        gt = _load_ground_truth()
        if item_id and item_id in gt:
            return {
                "is_hallucination": gt[item_id].get("is_hallucination", False),
                "type": gt[item_id].get("hallucination_type") or "无幻觉",
                "detail": gt[item_id].get("detail", "模拟结果"),
                "source": "mock"
            }
        return {"is_hallucination": False, "type": "未知", "detail": "Mock 默认", "source": "mock"}

    # ---------- 真实 API 模式 ----------
    try:
        client = OpenAI(
            base_url=config.BASE_URL,
            api_key=config.API_KEY,
        )

        # ===== 方案二：优化后的 Prompt（规避安全拦截） =====
        prompt = f"""
你是一个严谨的【文本事实核查工具】，而非健康顾问或客服人员。

你的唯一任务：**对比【客服回复】和【知识库】的内容，判断两者是否存在事实矛盾**。
请注意：
1. 不要提供任何医疗建议、安全评估或生活指导。
2. 只做客观的文本比对，如果回复编造了知识库中没有的信息、或与知识库明确冲突，即为幻觉。
3. 如果知识库为空或明确写"无"，而回复给出了具体信息，即为幻觉。

用户问题：{user_question}
客服回复：{system_reply}
知识库：{knowledge_base}

请严格输出以下 JSON 格式（不要包含任何其他说明文字）：
{{
  "is_hallucination": true/false,
  "type": "政策编造/参数编造/信息编造/能力越界/安全误导/信息遗漏偏差/无幻觉",
  "detail": "简短理由"
}}
"""
        response = client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=config.TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
        )
        content = response.choices[0].message.content

        # ===== 方案一：增强解析容错（应对空内容或非 JSON 格式） =====
        # 1. 判空处理（若触发安全拦截，直接按幻觉处理）
        if not content or not content.strip():
            utils.logger.warning(f"⚠️ API 返回空内容 (id={item_id})，疑似安全过滤，按幻觉处理")
            return {
                "is_hallucination": True,
                "type": "安全误导",
                "detail": "API返回空内容，疑似安全过滤，按幻觉处理以防漏报",
                "source": "llm_fallback"
            }

        # 2. 提取 JSON 片段（防止模型输出多余文字）
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = content

        # 3. 解析 JSON
        result = json.loads(json_str)
        result["source"] = "llm"
        return result

    except json.JSONDecodeError as e:
        utils.logger.error(f"❌ JSON 解析失败: {e}, 内容预览: {content[:100] if content else '空'}")
        # 降级：为了不漏报，按幻觉处理
        return {
            "is_hallucination": True,
            "type": "解析失败",
            "detail": f"响应无法解析为JSON，内容预览: {content[:50] if content else '空'}",
            "source": "parse_error"
        }
    except Exception as e:
        utils.logger.error(f"❌ LLM 调用失败: {e}")
        return None