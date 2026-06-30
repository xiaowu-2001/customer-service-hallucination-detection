import json
import logging
import sys


# -------------------- 日志配置 --------------------
def setup_logger():
    logger = logging.getLogger("HallucinationDetector")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    console.setFormatter(formatter)
    logger.addHandler(console)
    return logger


logger = setup_logger()


# -------------------- 文件读写（带容错） --------------------
def load_json(filepath):
    """加载 JSON，出错返回 None 并记录错误"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f, strict=False)
            logger.info(f"✅ 成功加载文件: {filepath} (共 {len(data)} 条记录)")
            return data
    except FileNotFoundError:
        logger.error(f"❌ 文件不存在: {filepath}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON 解析失败: {filepath} - {e}")
        return None


def save_json(data, filepath):
    """保存 JSON 文件"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 数据已保存: {filepath}")
    except Exception as e:
        logger.error(f"❌ 保存失败: {filepath} - {e}")