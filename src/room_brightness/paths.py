"""Keep personal calibration outside the source checkout."""

import os
from pathlib import Path

RESOURCE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "RoomBrightness"
