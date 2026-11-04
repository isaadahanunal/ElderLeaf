"""Test settings must be in the environment before any elderleaf module is imported."""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="elderleaf-test-")
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
        "STORAGE_BACKEND": "local",
        "STORAGE_DIR": f"{_tmp}/files",
        "SAM_CACHE_DIR": f"{_tmp}/sam",
        "JOB_MODE": "sync",
        "MODEL_API_KEY": "test-key-never-sent",
        "SCORE_THRESHOLD": "0.5",
        "ENABLE_LESION": "0",
        "PROMPT_STRATEGY": "fixed",  # tests that need the agent inject a fake LLM
        "BASETEN_API_KEY": "",
        "LLM_PROVIDER": "meta",
        "LLM_CACHE_DIR": f"{_tmp}/llm",
        "REPORT_AGENT": "0",  # template texts; report tests switch the writer on with a fake LLM
        "WEATHER": "0",  # no network in tests
        "WEATHER_CACHE_DIR": f"{_tmp}/weather",
    }
)
