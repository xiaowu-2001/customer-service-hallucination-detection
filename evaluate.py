"""
评估工具 v2.0 — 比对检测结果与人工标注

v2.0 变更:
- 适配多类型检测结果（识别 all_types 字段）
- 输出格式修正为 .txt（不再误导性地命名为 .json）
- 明细展示中包含多类型标签
"""

import config
import utils
from datetime import datetime


def evaluate():
    print("\n" + "=" * 60)
    print("📊 评估工具：比对检测结果与人工标注（含误判明细）")
    print("=" * 60 + "\n")

    # 1. 加载预测结果和真值
    pred = utils.load_json(config.OUTPUT_RESULT_PATH)
    truth = utils.load_json(config.GROUND_TRUTH_PATH)

    if pred is None or truth is None:
        utils.logger.error("❌ 无法加载预测或真值文件")
        return

    # 2. 构建真值字典
    truth_dict = {item["id"]: item for item in truth}

    # 3. 统计变量
    tp = fp = fn = tn = 0
    fp_details = []
    fn_details = []

    for p in pred:
        p_id = p["id"]
        p_hall = p.get("is_hallucination", False)
        t_item = truth_dict.get(p_id)
        if not t_item:
            continue
        t_hall = t_item.get("is_hallucination", False)

        # 构建预测的类型标签（含多类型）
        if p.get("all_types"):
            pred_type_str = " + ".join(f["type"] for f in p["all_types"])
        else:
            pred_type_str = p.get("type", "未知")

        if p_hall and t_hall:
            tp += 1
        elif p_hall and not t_hall:
            fp += 1
            fp_details.append({
                "id": p_id,
                "pred_type": pred_type_str,
                "truth_detail": t_item.get("detail", ""),
                "truth_type": t_item.get("hallucination_type") or "无幻觉",
            })
        elif not p_hall and t_hall:
            fn += 1
            fn_details.append({
                "id": p_id,
                "pred_type": pred_type_str,
                "truth_detail": t_item.get("detail", ""),
                "truth_type": t_item.get("hallucination_type") or "未知",
            })
        else:
            tn += 1

    # 4. 计算指标
    total = tp + fp + fn + tn
    accuracy = (tp + tn) / total if total else 0
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    # 5. 控制台输出
    print("📋 混淆矩阵:")
    print(f"              预测幻觉  预测非幻觉")
    print(f"真实幻觉      {tp:>6}      {fn:>6}")
    print(f"真实非幻觉    {fp:>6}      {tn:>6}\n")

    print("📈 评估指标:")
    print(f"  准确率 (Accuracy)  = {accuracy:.2%}")
    print(f"  精确率 (Precision) = {precision:.2%}")
    print(f"  召回率 (Recall)    = {recall:.2%}")
    print(f"  F1 值              = {f1:.4f}\n")

    if fp_details:
        print("❌ 误报 (FP) - 预测为幻觉，但实际不是幻觉：")
        for item in fp_details:
            print(f"  - ID: {item['id']}, 预测类型: {item['pred_type']}")
            print(f"    真实类型: {item['truth_type']}")
            print(f"    真实说明: {item['truth_detail'][:120]}...")
    else:
        print("✅ 无误报 (FP = 0)")

    if fn_details:
        print("\n❌ 漏报 (FN) - 预测非幻觉，但实际是幻觉：")
        for item in fn_details:
            print(f"  - ID: {item['id']}, 预测类型: {item['pred_type']}")
            print(f"    真实类型: {item['truth_type']}")
            print(f"    真实说明: {item['truth_detail'][:120]}...")
    else:
        print("✅ 无漏报 (FN = 0)")

    # 6. 生成文本报告
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    report_lines = [
        "=" * 60,
        "       客服幻觉检测 — 评估报告",
        "=" * 60,
        f"生成时间: {timestamp}",
        "",
        "【混淆矩阵】",
        f"                预测幻觉    预测非幻觉",
        f"  真实幻觉          {tp:>6}        {fn:>6}",
        f"  真实非幻觉        {fp:>6}        {tn:>6}",
        "",
        "【评估指标】",
        f"  准确率 (Accuracy)  = {accuracy:.2%}",
        f"  精确率 (Precision) = {precision:.2%}",
        f"  召回率 (Recall)    = {recall:.2%}",
        f"  F1 值              = {f1:.4f}",
        "",
    ]

    if fp_details:
        report_lines.append("【误报 (FP) 明细】")
        for item in fp_details:
            report_lines.append(f"  - ID: {item['id']}")
            report_lines.append(f"    预测类型: {item['pred_type']}")
            report_lines.append(f"    真实类型: {item['truth_type']}")
            report_lines.append(f"    真实说明: {item['truth_detail']}")
        report_lines.append("")
    else:
        report_lines.append("【误报 (FP) 明细】: 无")
        report_lines.append("")

    if fn_details:
        report_lines.append("【漏报 (FN) 明细】")
        for item in fn_details:
            report_lines.append(f"  - ID: {item['id']}")
            report_lines.append(f"    预测类型: {item['pred_type']}")
            report_lines.append(f"    真实类型: {item['truth_type']}")
            report_lines.append(f"    真实说明: {item['truth_detail']}")
        report_lines.append("")
    else:
        report_lines.append("【漏报 (FN) 明细】: 无")
        report_lines.append("")

    report_content = "\n".join(report_lines)

    # 写入文本文件
    try:
        with open(config.EVALUATION_REPORT_PATH, 'w', encoding='utf-8') as f:
            f.write(report_content)
        utils.logger.info(f"📄 详细报告已保存至: {config.EVALUATION_REPORT_PATH}")
    except Exception as e:
        utils.logger.error(f"❌ 报告保存失败: {e}")


if __name__ == "__main__":
    evaluate()
