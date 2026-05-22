import logging

from app.core.config import settings


# logging_config.py 阅读地图：
# 1. LOG_FORMAT 定义每行日志长什么样。
# 2. setup_logging() 根据 .env 里的 LOG_LEVEL 初始化 Python logging。
# 3. 其他文件后续如果需要日志，可以用 logging.getLogger(__name__) 获取 logger。

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def setup_logging() -> None:
    level_name = settings.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        force=True,
    )

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
