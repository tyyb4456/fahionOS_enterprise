"""
FashionOS Backend Logging Configuration
========================================
Provides standard logging configuration for all backend modules.
"""
import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Configures root logger format and handlers for stdout."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """Returns a module logger configured under the fashionos namespace."""
    return logging.getLogger(name)
