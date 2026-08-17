"""
utils/logger.py
===============
Configuração de logging para o pipeline.
"""
import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logger(log_dir: Path, level: str = "INFO") -> logging.Logger:
    """Configura logger com saída em console e arquivo."""
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str  = datetime.now().strftime("%Y%m%d")
    log_file  = log_dir / f"pipeline_{date_str}.log"

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    return logging.getLogger("pipeline")
