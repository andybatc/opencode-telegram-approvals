import logging
from .config import load_config

def main():
    cfg = load_config()
    logging.basicConfig(
        level=getattr(logging, cfg.bridger_log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger(__name__).info("Bridger starting...")
    # TODO: wire up SSE listener + telegram bot
    pass

if __name__ == "__main__":
    main()