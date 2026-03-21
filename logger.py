import logging

_FMT = "%(asctime)s | %(levelname)-5s | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(format=_FMT, datefmt=_DATE_FMT, level=logging.INFO)

logging.getLogger("TeleBot").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

log = logging.getLogger("yme_bot")
