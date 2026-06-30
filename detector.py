"""
客服幻觉检测工具 v2.0 — 规则 + LLM 混合检测

v2.0 变更:
- 适配 rules.py 的多类型返回值（list[dict]）
- 规则命中多条时合并展示，保留 all_types 供分析
"""

import config
import utils
from rules import check_rules
from llm_client import call_llm


def main():
    print("\n" + "=" * 50)
    print("🚀 客服幻觉检测工具 v2.0 (规则+LLM混合检测)")
    print("=" * 50 + "\n")

    # 加载数据
    replies = utils.load_json(config.REPLIES_PATH)
    if replies is None:
        return

    results = []
    rule_hit_count = 0
    llm_hit_count = 0
    multi_type_count = 0

    for item in replies:
        item_id = item["id"]
        user_q = item["user_question"]
        sys_r = item["system_reply"]
        kb = item["knowledge_base"]

        # ─── 1. 规则检测（返回列表） ───
        rule_findings = check_rules(sys_r, kb)

        if rule_findings:
            # 规则命中（可能多条）
            rule_hit_count += 1
            if len(rule_findings) > 1:
                multi_type_count += 1

            # 以严重程度排序，最严重的作为主类型
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}
            rule_findings.sort(key=lambda f: severity_order.get(f.get("severity", "unknown"), 4))

            primary = rule_findings[0]
            result = {
                "id": item_id,
                "is_hallucination": True,
                "type": primary["type"],
                "detail": primary["detail"],
                "source": "rule",
            }
            # 如果有多条，附加完整列表
            if len(rule_findings) > 1:
                result["all_types"] = rule_findings
                type_list = " + ".join(f["type"] for f in rule_findings)
                utils.logger.info(f"✅ {item_id} -> 规则命中 ({len(rule_findings)}条): {type_list}")
            else:
                utils.logger.info(f"✅ {item_id} -> 规则命中: {primary['type']}")

            results.append(result)
            continue

        # ─── 2. LLM 检测（规则未命中时回退） ───
        llm_result = call_llm(user_q, sys_r, kb, item_id)
        if llm_result is None:
            llm_result = {
                "id": item_id,
                "is_hallucination": False,
                "type": "未知",
                "detail": "LLM 调用失败，默认非幻觉",
                "source": "fallback",
            }
        else:
            llm_result["id"] = item_id

        results.append(llm_result)
        llm_hit_count += 1
        utils.logger.info(f"🤖 {item_id} -> LLM 判断: {llm_result.get('is_hallucination')} ({llm_result.get('type')})")

    # ─── 3. 保存结果 ───
    utils.save_json(results, config.OUTPUT_RESULT_PATH)

    # ─── 4. 统计 ───
    total = len(results)
    hallucination_count = sum(1 for r in results if r.get("is_hallucination"))
    print(f"\n📊 检测完成: 共 {total} 条，其中幻觉 {hallucination_count} 条")
    print(f"   规则命中: {rule_hit_count} 条（含多类型: {multi_type_count} 条）")
    print(f"   LLM 判断: {llm_hit_count} 条")
    print(f"💾 结果已保存至: {config.OUTPUT_RESULT_PATH}")


if __name__ == "__main__":
    main()
