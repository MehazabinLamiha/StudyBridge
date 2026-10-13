"""Run StudyBridge from any working directory: python path/to/run.py [options] <command>."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from studybridge.cli import main  # noqa: E402

main()
