"""Logging setup."""

import logging
import sys

from lib.config import LOG_DIR


def setup_logging() -> logging.Logger:
    """Initialise and return the application logger."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / "tasks").mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("asana_poller")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    fh = logging.FileHandler(LOG_DIR / "poller.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger
