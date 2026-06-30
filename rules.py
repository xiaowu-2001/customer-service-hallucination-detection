"""
规则引擎 v2.0 — 多类型幻觉检测

变更说明 (相比 v1.0):
1. 修复 h07 正则 Bug: "地址.*" 无法匹配 "退货请寄到..." → 改用 "(?:退货|地址).*"
2. 支持多类型检测: 不再命中第一条就 return，而是收集所有匹配的规则
3. 移除过度拟合的硬编码字符串（能力越界检测中的 '南京转运'/'北京' 等）
4. 增强字符串匹配鲁棒性（如 '无' 误匹配 '无门槛券'）
5. 每条规则附带严重程度 (severity)
"""

import re
from typing import List, Dict, Optional

# ============================================================
# 严重程度定义
# ============================================================
SEVERITY = {
    "安全误导": "critical",   # 可能造成人身伤害
    "参数编造": "high",       # 产品核心信息错误
    "政策编造": "high",       # 交易政策虚构
    "优惠编造": "medium",     # 营销活动虚构
    "能力越界": "medium",     # 假装具备系统不具备的能力
    "信息编造": "medium",     # 编造不存在的事实信息
    "政策偏差": "low",        # 政策部分正确部分错误
    "信息遗漏": "low",        # 遗漏关键信息导致建议不准确
}


def check_rules(reply: str, kb: str) -> List[Dict]:
    """
    检测单条回复中的全部幻觉类型（不再提前 return）

    参数:
        reply: 客服系统回复文本
        kb:    知识库参考文本

    返回:
        List[Dict]: 所有命中的幻觉类型，每项包含 type / detail / severity
                    空列表 = 规则未命中，需交给 LLM 判断
    """
    reply_lower = reply.lower()
    kb_lower = kb.lower() if isinstance(kb, str) else ""
    findings: List[Dict] = []

    # ============================================================
    # 辅助函数
    # ============================================================
    def add_finding(h_type: str, detail: str):
        """向 findings 列表添加一条检测结果"""
        findings.append({
            "type": h_type,
            "detail": detail,
            "severity": SEVERITY.get(h_type, "unknown"),
        })

    def kb_has_keyword(keyword: str) -> bool:
        """检查知识库中是否包含某关键词（精确边界匹配，避免子串误判）"""
        return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", kb) is not None

    # ============================================================
    # 类型1：政策编造 — 退货/换货天数冲突
    # ============================================================
    reply_days = re.search(r"(\d+)\s*天.*?无理由", reply)
    kb_days = re.search(r"(\d+)\s*天.*?无理由", kb)
    if reply_days and kb_days:
        if reply_days.group(1) != kb_days.group(1):
            add_finding("政策编造",
                f"回复称{reply_days.group(1)}天无理由退货，知识库为{kb_days.group(1)}天")

    # ============================================================
    # 类型2：参数编造 — 产品参数与知识库矛盾
    # ============================================================

    # 2.1 蓝牙版本
    reply_bt = re.search(r"蓝牙\s*(\d+\.?\d*)", reply)
    kb_bt = re.search(r"蓝牙\s*(\d+\.?\d*)", kb)
    if reply_bt and kb_bt and reply_bt.group(1) != kb_bt.group(1):
        add_finding("参数编造",
            f"回复蓝牙{reply_bt.group(1)}，知识库为{kb_bt.group(1)}")

    # 2.2 接口类型冲突（Type-C vs USB-A）
    has_type_c = "type-c" in reply_lower or "type c" in reply_lower
    has_usb_a = "usb-a" in kb_lower or "usb a" in kb_lower
    if has_type_c and has_usb_a:
        add_finding("参数编造", "回复称Type-C接口，知识库为USB-A")
    if ("usb-a" in reply_lower or "usb a" in reply_lower) and ("type-c" in kb_lower or "type c" in kb_lower):
        add_finding("参数编造", "回复称USB-A接口，知识库为Type-C")

    # 2.3 核心材质冲突
    leather_keywords_reply = ("头层牛皮" in reply or "真皮" in reply or "头层" in reply)
    leather_keywords_kb = ("pu合成革" in kb_lower or ("pu" in kb_lower and "合成" in kb))
    if leather_keywords_reply and leather_keywords_kb:
        add_finding("参数编造", "回复宣称头层牛皮/真皮，知识库为PU合成革")

    # 2.4 保修期冲突
    reply_warranty = re.search(r"保修[期为]?\s*(\d+)\s*(个?月|年)?", reply)
    kb_warranty = re.search(r"保修[期为]?\s*(\d+)\s*(个?月|年)?", kb)
    if reply_warranty and kb_warranty:
        r_num = int(reply_warranty.group(1))
        k_num = int(kb_warranty.group(1))
        # 单位换算：年 → 月
        if reply_warranty.group(2) and "年" in reply_warranty.group(2):
            r_num *= 12
        if kb_warranty.group(2) and "年" in kb_warranty.group(2):
            k_num *= 12
        if r_num != k_num:
            add_finding("参数编造",
                f"回复保修{r_num}个月，知识库为{k_num}个月")

    # 2.5 NFC / 功能参数：知识库标注"未标注"而回复确认有
    if ("支持" in reply or "有" in reply) and "未标注" in kb:
        # 提取被讨论的功能名（如 NFC）
        func_match = re.search(r"(NFC|nfc|蓝牙|GPS|Wi-Fi|无线充电|快充|防水)", reply)
        if func_match:
            add_finding("参数编造",
                f"知识库未标注{func_match.group(1)}功能，回复声称支持")

    # ============================================================
    # 类型3：政策偏差 — 部分正确但存在关键错误
    # ============================================================

    # 3.1 发货时间冲突
    reply_hours = re.search(r"(\d+)\s*小时.*?发", reply)
    kb_hours = re.search(r"(\d+)\s*小时.*?发", kb)
    if reply_hours and kb_hours and reply_hours.group(1) != kb_hours.group(1):
        add_finding("政策偏差",
            f"回复{reply_hours.group(1)}小时发货，知识库为{kb_hours.group(1)}小时")

    # 3.2 快递公司冲突
    express_keywords = ["顺丰", "中通", "韵达", "圆通", "京东", "邮政", "申通", "百世"]
    reply_expr = [e for e in express_keywords if e in reply]
    kb_expr = [e for e in express_keywords if e in kb]
    if reply_expr and kb_expr and set(reply_expr) != set(kb_expr):
        add_finding("政策偏差",
            f"回复称{','.join(reply_expr)}，知识库为{','.join(kb_expr)}")

    # 3.3 发票类型冲突
    if "纸质发票" in reply and ("暂不支持纸质" in kb or "不支持纸质发票" in kb):
        add_finding("政策偏差", "回复称支持纸质发票，知识库暂不支持")
    if "电子发票" in reply and "不支持电子发票" in kb:
        add_finding("政策偏差", "回复称支持电子发票，知识库不支持")

    # 3.4 申请方式冲突（如"备注" vs "订单详情页"）
    if "备注" in reply and "订单详情页" in kb:
        add_finding("政策偏差", "回复指引在备注填写，知识库要求在订单详情页申请")

    # ============================================================
    # 类型4：优惠编造 — 虚构不存在的优惠活动
    # ============================================================

    # 4.1 满减优惠券编造
    reply_coupon = re.search(r"满(\d+)减(\d+)", reply)
    if reply_coupon:
        r_amount = reply_coupon.group(1)
        r_discount = reply_coupon.group(2)
        # 情况A：知识库明确否定该金额的优惠（如 "无满300减50的活动"）
        kb_explicitly_negates = bool(re.search(rf"无满{r_amount}减", kb))
        # 情况B：知识库列出了可用优惠券，但回复的券不在其中
        kb_coupons = re.findall(r"满(\d+)减(\d+)", kb)
        # 过滤掉被"无"否定的券（如 "无满300减50"）
        kb_valid_coupons = [
            (a, d) for a, d in kb_coupons
            if not re.search(rf"无满{a}减{d}", kb)
        ]
        kb_has_other_coupons = len(kb_valid_coupons) > 0
        reply_coupon_not_in_valid = (r_amount, r_discount) not in kb_valid_coupons

        if kb_explicitly_negates:
            add_finding("优惠编造",
                f"回复称有满{r_amount}减{r_discount}券，知识库明确无此活动")
        elif kb_has_other_coupons and reply_coupon_not_in_valid:
            valid_strs = [f"满{a}减{d}" for a, d in kb_valid_coupons]
            add_finding("优惠编造",
                f"回复称有满{r_amount}减{r_discount}券，知识库仅有{', '.join(valid_strs)}")

    # 4.2 学生优惠编造
    has_student_reply = "学生优惠" in reply or "学生认证" in reply or "学生证" in reply
    has_student_kb = "学生优惠" in kb or "学生" in kb
    if has_student_reply and ("无学生优惠" in kb or ("无" in kb and not has_student_kb)):
        add_finding("优惠编造", "回复称有学生优惠，知识库明确无此政策")

    # ============================================================
    # 类型5：信息编造 — 编造知识库中不存在的事实
    # ============================================================

    # 5.1 线下门店编造
    has_offline_reply = ("线下" in reply and ("门店" in reply or "体验店" in reply or "实体店" in reply))
    has_online_only_kb = "纯线上" in kb or "无线下" in kb or "线上电商" in kb
    if has_offline_reply and has_online_only_kb:
        add_finding("信息编造", "回复称有线下门店，知识库为纯线上品牌")

    # 5.2 退货地址编造 — 修复 h07 Bug
    #     原正则为 r"地址.*[省市]..." 无法匹配以"退货请寄到"开头的回复
    if re.search(r"(?:退货请|退货地址|地址)[^。]*[省市][^。]*[路街]", reply) \
       and ("自动匹配" in kb or "短信发送" in kb or "不可口头告知" in kb):
        add_finding("信息编造",
            "回复给出了具体退货地址，知识库要求系统匹配后短信发送/不可口头告知")

    # 5.3 品牌关联编造
    if ("子品牌" in reply or "旗下" in reply) and ("未提及" in kb or "无关联" in kb):
        add_finding("信息编造", "回复编造了品牌关联关系，知识库无此信息")

    # ============================================================
    # 类型6：能力越界 — 系统不具备某能力，回复却假装执行了
    #
    # 设计思路（v2.1 重写）：
    #   - 旧版用 \d+ 匹配任何数字，会误判诚实拒绝（如 "请拨400电话咨询"）
    #   - 新版分三步：KB声明无能力 → 排除诚实拒绝 → 检测伪装信号
    #
    # 诚实拒绝特征：明确说"做不到"（无法/不能/暂无此功能）
    # 伪装执行特征：声称已完成操作 / 给出具体地址 / 时间承诺 / 状态断言
    # ============================================================
    kb_has_no_capability = (
        "未接入" in kb
        or "不具备" in kb
        or re.search(r"无[（(]客服系统", kb) is not None
        or "无接口" in kb
    )

    if kb_has_no_capability:
        # ── 第一步：排除诚实拒绝 ──
        # 如果回复明确承认"我做不到"，即使含数字也不算越界
        honest_refusal = bool(re.search(
            r"无法|不能|暂无(?:法|此功能)|暂不支持|没有权限|超出能力",
            reply
        ))
        if not honest_refusal:
            # ── 第二步：检测伪装信号 ──
            signals_detected = []

            # 信号A：声称已执行操作（已/已经/正在 + 动词性短语）
            if re.search(r"(?:已|已经|正在)\s*[一-鿿]{1,6}", reply):
                signals_detected.append("声称已执行操作")

            # 信号B：提供不应有的具体地址（省/市 + 路/街/号/巷）
            if re.search(r"[省市区][^，。；]{0,15}[路街号巷]", reply):
                signals_detected.append("提供具体地址")

            # 信号C：给出时间预测/承诺（系统不应知道的时间）
            if re.search(
                r"(?:预计|将于|会在?)\s*(?:明天|今天|后天|下周|下月"
                r"|\d+天[内后前]|\d+小时[内后]|\d+月\d+日)",
                reply
            ):
                signals_detected.append("给出时间预测")

            # 信号D：断言当前具体状态（目前/当前 + 在/处于）
            if re.search(r"(?:目前|当前|现在)(?:在|位于|处于|已)", reply):
                signals_detected.append("断言当前状态")

            # 信号E：给出带时限的具体承诺（N小时内联系/处理/回复）
            if re.search(
                r"\d+\s*(?:小时|天|分钟|个工作日)\s*(?:内|之内|后)?"
                r"(?:联系|处理|回复|到账|送达|发出|完成|上门)",
                reply
            ):
                signals_detected.append("给出时限承诺")

            if signals_detected:
                add_finding("能力越界",
                    f"知识库明确系统无此能力，回复却{'；'.join(signals_detected)}")

    # ============================================================
    # 类型7：安全误导 — 忽视风险提示，给出可能危害健康的建议
    # ============================================================
    has_health_claim = (
        ("孕妇" in reply or "哺乳" in reply or "孕妈" in reply)
        and ("放心" in reply or "可以" in reply or "安全" in reply or "适合" in reply)
    )
    has_risk_warning = (
        "视黄醇" in kb
        or "慎用" in kb
        or "咨询医生" in kb
        or "不建议" in kb
        or "遵医嘱" in kb
    )
    if has_health_claim and has_risk_warning:
        add_finding("安全误导",
            "知识库提示含风险成分/需咨询医生，回复却声称可以放心使用")

    # ============================================================
    # 类型8：信息遗漏 — 忽略知识库中的关键信息
    # ============================================================
    # 尺码建议冲突：知识库说偏大/偏小，回复说标准
    if re.search(r"(?:偏大|偏小|偏窄|偏宽)", kb) \
       and re.search(r"(?:标准|不偏|正常)", reply):
        add_finding("信息遗漏",
            "知识库有用户反馈尺码偏差，回复却说标准不偏（遗漏关键信息）")

    # ============================================================
    # 返回全部命中结果
    # ============================================================
    return findings
