from loguru import logger


logger.add(
    "logs/stock_ai_assistant.log",
    rotation="10 MB",
    retention="7 days",
    backtrace=True,
    diagnose=False,
    enqueue=True,
)

__all__ = ["logger"]

