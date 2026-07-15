"""Local development launcher.

Exists because of one Windows quirk: psycopg's async driver cannot run on the
ProactorEventLoop, which is Python's default on Windows. The policy must be set
before uvicorn creates its loop, and uvicorn builds the loop before importing
the app -- so setting it inside app/main.py would be too late.

In Docker the app runs on Linux and this script is unnecessary; the container
invokes uvicorn directly.

    python run_local.py
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn  # noqa: E402  -- must come after the policy is set

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_config=None,  # app.core.logging owns log configuration
    )
