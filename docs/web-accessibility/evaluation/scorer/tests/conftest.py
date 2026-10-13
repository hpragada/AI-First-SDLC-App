"""Make the scorer importable without it ever becoming a package under `backend/`.

INTERNAL — Edvensoft accessibility evaluation.

Deliberately a path insert rather than an installed package. One of QA-10a's acceptance
criteria is that a search of the repository proves no tenant-facing code references this
harness, and the cheapest way to keep that true is for the harness not to be importable from
anywhere the platform can reach.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
