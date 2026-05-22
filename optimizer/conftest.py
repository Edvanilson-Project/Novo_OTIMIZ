import os

# Ensure tests never fail on missing env vars for security keys.
# The real validator rejects the known-bad default — this key is for tests only.
os.environ.setdefault("INTERNAL_OPTIMIZER_KEY", "test-strong-key-for-pytest-32chars-ok")
os.environ.setdefault("BACKEND_SECRET", "test-backend-secret-for-pytest-ci-only")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
