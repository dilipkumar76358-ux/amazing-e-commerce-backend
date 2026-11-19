import sys
from pathlib import Path

# Add backend directory to sys.path so app imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
