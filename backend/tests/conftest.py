import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

# Force deterministic test credentials; env vars override .env for pytest runs.
os.environ["DUMMY_EMAIL"] = "demo@homescout.ai"
os.environ["DUMMY_PASSWORD"] = "password123"
os.environ["ACCESS_TOKEN"] = "test-access-token-for-pytest"

from src.core.config import get_settings

get_settings.cache_clear()

TEST_DUMMY_EMAIL = os.environ["DUMMY_EMAIL"]
TEST_DUMMY_PASSWORD = os.environ["DUMMY_PASSWORD"]
TEST_ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
