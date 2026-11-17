from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
MEMORY_DIR = BACKEND_DIR / "memory"
SHOT_DIR = BACKEND_DIR / "data" / "browser-agent" / "shots"
