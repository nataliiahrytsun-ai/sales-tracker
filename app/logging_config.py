"""Minimal centralized application logging configuration."""

import logging

APPLICATION_LOGGER_NAME = "sales_tracker"
LOG_FORMAT = "%(levelname)s [%(name)s] %(message)s"
_HANDLER_MARKER = "_sales_tracker_console_handler"


def configure_application_logging(level: str) -> logging.Logger:
    """Configure one idempotent stderr handler for application events."""
    logger = logging.getLogger(APPLICATION_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    handler = next(
        (
            existing_handler
            for existing_handler in logger.handlers
            if getattr(existing_handler, _HANDLER_MARKER, False)
        ),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler()
        setattr(handler, _HANDLER_MARKER, True)
        logger.addHandler(handler)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    return logger
