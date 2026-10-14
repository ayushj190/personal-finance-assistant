import logging
import os
from pathlib import Path
import unittest

from core.config import DATA_DIR
from core import logging_setup
class TestLoggingSetup(unittest.TestCase):
    def test_logging_configuration(self):
        logging_setup.configure()
        logger = logging.getLogger("test_logger")
        logger.info("Test log message from test_logging")

        log_file = DATA_DIR / "logs" / "app.log"
        self.assertTrue(log_file.exists())
        content = log_file.read_text(encoding="utf-8")
        self.assertIn("Test log message from test_logging", content)


if __name__ == "__main__":
    unittest.main()
