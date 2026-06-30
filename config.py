import os

# -------------------- API 配置（已按你的要求填写） --------------------
BASE_URL = "https://api.agicto.cn/v1"
# 建议从环境变量读取，避免硬编码；如果直接运行测试，请把下方引号内替换成你的 key
API_KEY = os.getenv("OPENAI_API_KEY", "sk-QxCtUIvAdqeGYCmUsjHpYrufTT81hp1bb92HdAI6QhJGnPiq")

# -------------------- 模型与模式 --------------------
# 注意：api.agicto.cn 通常支持 gpt-3.5-turbo 或 gpt-4，请根据实际代理的模型填写
MODEL_NAME = "gpt-5-chat-latest"
TEMPERATURE = 0.1
MAX_TOKENS = 300

# Mock 模式：第一阶段先开 True，确保不消耗 API 也能跑通流程
MOCK_MODE = False

# -------------------- 文件路径（始终基于脚本所在目录，不受 CWD 影响） --------------------
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

REPLIES_PATH = os.path.join(_BASE_DIR, "task4_replies.json")
GROUND_TRUTH_PATH = os.path.join(_BASE_DIR, "task4_ground_truth.json")
OUTPUT_RESULT_PATH = os.path.join(_BASE_DIR, "result.json")
EVALUATION_REPORT_PATH = os.path.join(_BASE_DIR, "evaluation_report.txt")