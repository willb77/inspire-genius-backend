import logging
import logging.handlers
import os
import sys
import json


# Define the log directory at the root of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def get_log_formatter(json_format=False):
    if json_format:
        return logging.Formatter(json.dumps({
            "time": "%(asctime)s",
            "level": "%(levelname)s",
            "name": "%(name)s",
            "message": "%(message)s"
        }))
    else:
        return logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )


def setup_logger(name=None, level=logging.INFO, json_format=False):
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger  # Prevent duplicate handlers

    logger.setLevel(level)

    formatter = get_log_formatter(json_format)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Info Log Handler (main log - INFO and above)
    info_log_file = os.path.join(LOG_DIR, "info.log")
    info_handler = logging.handlers.RotatingFileHandler(
        info_log_file, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    info_handler.setFormatter(formatter)
    info_handler.setLevel(logging.INFO)
    logger.addHandler(info_handler)

    # Error Log Handler (ERROR level only)
    error_log_file = os.path.join(LOG_DIR, "error.log")
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    logger.addHandler(error_handler)

    # Warning Log Handler (WARNING level only)
    warning_log_file = os.path.join(LOG_DIR, "warning.log")
    warning_handler = logging.handlers.RotatingFileHandler(
        warning_log_file, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    warning_handler.setFormatter(formatter)
    warning_handler.setLevel(logging.WARNING)
    # Add filter to only capture WARNING level messages
    warning_handler.addFilter(lambda record: record.levelno == logging.WARNING)
    logger.addHandler(warning_handler)

    return logger


logger = setup_logger('Prism', True)
