from __future__ import annotations

import logging
import os
import sys
import warnings


def setup_logging(logfile: str = "logs/news_breakout.log") -> logging.Logger:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="yfinance")
    os.makedirs(os.path.dirname(logfile) or ".", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(logfile, encoding="utf-8")],
    )
    return logging.getLogger("news_breakout")
