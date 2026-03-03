"""
config.py

This module loads project configurations from a .env file or environment variables, 
providing convenient access to paths, dates, and credentials (e.g., WRDS_USERNAME).
It is intended to be imported as a module, but it can also be run as a standalone 
script to ensure the required directories are created.

For more information on the rationale behind decouple, see:
https://pypi.org/project/python-decouple/
"""

from decouple import config
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def _resolve(raw, default):
    """Resolve a path string relative to BASE_DIR if not absolute."""
    if raw is None:
        return default
    p = Path(raw)
    return p if p.is_absolute() else (BASE_DIR / p).resolve()

WRDS_USERNAME = config("WRDS_USERNAME", default="")
MANUAL_DATA = _resolve(config('MANUAL_DATA', default=None), BASE_DIR / 'data_manual')
DATA_DIR    = _resolve(config('DATA_DIR',    default=None), BASE_DIR / '_data')
OUTPUT_DIR  = _resolve(config('OUTPUT_DIR',  default=None), BASE_DIR / '_output')
START_DATE = config('START_DATE', default='1960-01-01')
END_DATE = config('END_DATE', default='2012-12-31')
UPDATED_END_DATE = config('UPDATED_END_DATE', default='2025-01-01')

def ensure_directories():
    """
    Creates the necessary directories for data and output if they do not exist.
    Specifically, it ensures that:
      1) DATA_DIR/pulled
      2) DATA_DIR/manual
      3) OUTPUT_DIR
    are available.
    """
    (DATA_DIR / 'pulled').mkdir(parents=True, exist_ok=True)
    (DATA_DIR / 'manual').mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    """
    Running this file directly will call ensure_directories() and print out 
    the essential configuration parameters and paths.
    """
    ensure_directories()

    print("Directories ensured:")
    print(f"  - DATA_DIR: {DATA_DIR}")
    print(f"  - OUTPUT_DIR: {OUTPUT_DIR}")
    print(f"WRDS_USERNAME: {WRDS_USERNAME}")
