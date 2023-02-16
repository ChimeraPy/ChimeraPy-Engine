# Setup the logging for the library
# References:
# https://docs.python-guide.org/writing/logging/
# https://stackoverflow.com/questions/13649664/how-to-use-logging-with-pythons-fileconfig-and-configure-the-logfile-filename
import logging.config
import os
from dataclasses import dataclass
from typing import Any, Dict

from zmq.log.handlers import PUBHandler


@dataclass
class ZMQLogHandlerConfig:
    """Configuration for the log publishing via ZMQ Sockets."""

    publisher_port: int = 8687
    transport: str = "ws"
    root_topic: str = "chimerapy_logs"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        kwargs = {
            "publisher_port": d.get("publisher_port", 8687),
            "transport": d.get("publisher_transport", "ws"),
            "root_topic": d.get("publisher_root_topic", "chimerapy_logs"),
        }
        return cls(**kwargs)


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "formatter": "standard",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",  # Default is stderr
        },
    },
    "loggers": {
        "chimerapy": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": True,
        },
        "chimerapy-worker": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": True,
        },
        "chimerapy-networking": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": True,
        },
        "chimerapy-subprocess": {
            "handlers": [],
            "level": "DEBUG",
            "propagate": True,
        },
    },
}


# Setup the logging configuration
def setup():

    # Setting up the configureation
    logging.config.dictConfig(LOGGING_CONFIG)


def add_zmq_handler(logger: logging.Logger, handler_config: ZMQLogHandlerConfig):
    """Add a ZMQ log handler to the logger.

    Note:
        Uses the same formatter as the consoleHandler
    """
    # Add a handler to publish the logs to zmq ws
    handler = PUBHandler(
        f"{handler_config.transport}://*:{handler_config.publisher_port}"
    )
    handler.root_topic = handler_config.root_topic
    logger.addHandler(handler)
    handler.setLevel(logging.DEBUG)
    # Use the same formatter as the console
    handler.setFormatter(
        logging.Formatter(
            logger.handlers[0].formatter._fmt,
            logger.handlers[0].formatter.datefmt,
        )
    )  # FIXME: This is a hack, can this be done better?


def getLogger(
    name: str,
) -> logging.Logger:

    # Get the logging
    logger = logging.getLogger(name)

    # Ensure that the configuration is set
    debug_loggers = os.environ.get("CHIMERAPY_DEBUG_LOGGERS", "").split(os.pathsep)
    if name in debug_loggers:
        logger.setLevel(logging.DEBUG)

    return logger
