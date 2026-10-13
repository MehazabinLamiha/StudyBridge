"""StudyBridge: a cross-border and student finance assistant (sandbox)."""
from pathlib import Path

__version__ = "0.1.0"
PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_PROFILE = PROJECT_ROOT / "data" / "sample_profile.json"
