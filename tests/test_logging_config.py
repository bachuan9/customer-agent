import logging

from app.core.config import settings
from app.core.logging_config import setup_logging


def test_setup_logging_uses_configured_log_level():
    original_level = settings.log_level

    try:
        settings.log_level = "DEBUG"
        setup_logging()

        assert logging.getLogger().level == logging.DEBUG
    finally:
        settings.log_level = original_level
        setup_logging()

