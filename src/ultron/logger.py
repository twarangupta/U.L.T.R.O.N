"""The shared 'ultron' logger: INFO to the console, everything to ultron.log (5 MB, 5 backups)."""

import logging
import logging.handlers
import sys

from ultron import paths

# central logger instance
logger = logging.getLogger("ultron")
logger.setLevel(logging.DEBUG)

def setup_logger():
    """Sets up console and rotating file logging."""
    if logger.handlers:
        # Logger is already configured
        return logger

    # Log formatters
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler (prints info and above)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(fmt="[%(levelname)s] %(message)s"))
    logger.addHandler(console_handler)

    # Rotating File handler (all debug logs, max 5MB, keeps last 5 backups)
    log_file = paths.LOG_FILE
    
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"[Warning] Failed to initialize file logging: {e}")

    return logger

# Initialize logger immediately on import
setup_logger()
