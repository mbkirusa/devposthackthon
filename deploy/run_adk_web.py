from __future__ import annotations

import os


def main() -> None:
    port = os.getenv("PORT", "8080")
    os.execvp(
        "adk",
        [
            "adk",
            "web",
            "startup_ops_agent",
            "--host",
            "0.0.0.0",
            "--port",
            port,
            "--no-reload",
            "--session_service_uri",
            "memory://",
            "--artifact_service_uri",
            "memory://",
        ],
    )


if __name__ == "__main__":
    main()
