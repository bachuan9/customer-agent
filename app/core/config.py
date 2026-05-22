import os

from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv()


# config.py 阅读地图：
# 1. load_dotenv() 读取本地 .env。
# 2. read_bool_env(...) 把字符串环境变量转成布尔值。
# 3. Settings 集中保存项目名、日志、LLM、DeepSeek、Embedding 等配置。
# 4. 其他模块统一 import settings，避免到处直接读 os.getenv。


# 1. 布尔环境变量读取：把 true/false、1/0 这类字符串转成 Python bool。
def read_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# 2. 项目配置对象：后端启动后全局复用这份 settings。
class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "Ecom Service Agent")
    app_env: str = os.getenv("APP_ENV", "dev")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    llm_enabled: bool = read_bool_env("LLM_ENABLED", False)
    llm_provider: str = os.getenv("LLM_PROVIDER", "deepseek")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-v4-flash")
    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "20"))
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "local_hash")


settings = Settings()
