"""Ensures the project root is importable as `src`/`data` regardless of how
pytest is invoked (bare `pytest`, `python -m pytest`, from CI, etc.).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
