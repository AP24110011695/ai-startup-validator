"""Force mock mode for the whole test suite, regardless of the developer's .env.

Runs before any backend import (pytest loads conftest first), and config reads
env vars at import time. .env values cannot override these (load_dotenv does not
touch vars that already exist in the environment).
"""
import os

os.environ["USE_MOCK"] = "true"
os.environ.pop("FAKE_QUOTA_ERROR", None)
