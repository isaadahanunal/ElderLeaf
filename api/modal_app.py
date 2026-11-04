"""Deploy the ElderLeaf API on Modal.

    pip install modal && modal setup                      # once
    modal secret create elderleaf \\
        MODEL_API_KEY=... BASETEN_API_KEY=... \\
        DATABASE_URL=postgresql://postgres:...@...supabase.com:5432/postgres \\
        STORAGE_BACKEND=supabase SUPABASE_URL=https://xxxx.supabase.co SUPABASE_SERVICE_KEY=... \\
        CORS_ORIGINS=https://your-app.vercel.app
    cd api && modal deploy modal_app.py                   # prints the https://...modal.run URL

One always-on container runs the API and the analysis threads (uploads return at once and the
browser polls). Photos, videos and results live in Supabase, so the container can be replaced at
any time. SAM and LLM answers are cached on a Modal Volume so re-runs never pay twice.
"""

from pathlib import Path

import modal

HERE = Path(__file__).parent

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("ffmpeg")
    .pip_install_from_pyproject(str(HERE / "pyproject.toml"))
    .env({"SAM_CACHE_DIR": "/cache/sam", "LLM_CACHE_DIR": "/cache/llm", "JOB_MODE": "thread"})
    .add_local_python_source("elderleaf")
)

cache = modal.Volume.from_name("elderleaf-cache", create_if_missing=True)
app = modal.App("elderleaf-api", image=image)


@app.function(
    secrets=[modal.Secret.from_name("elderleaf")],
    volumes={"/cache": cache},
    min_containers=1,  # keep the background analysis threads alive between requests
    max_containers=1,
    scaledown_window=1200,
    timeout=900,
)
@modal.concurrent(max_inputs=64)
@modal.asgi_app()
def web():
    from elderleaf.app import app as fastapi_app

    return fastapi_app
