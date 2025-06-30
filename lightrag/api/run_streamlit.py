#!/usr/bin/env python
"""Launch the standalone Streamlit UI for LightRAG."""

import os
import subprocess
import sys
import pipmaster as pm


def check_and_install_dependencies():
    required_packages = [
        "streamlit",
        "streamlit-chatbox",
    ]
    for package in required_packages:
        if not pm.is_installed(package):
            print(f"Installing {package}...")
            pm.install(package)
            print(f"{package} installed successfully")


def main():
    check_and_install_dependencies()
    streamlit_cmd = [
        "streamlit",
        "run",
        os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "lightrag_streamlit",
                "app.py",
            )
        ),
        "--server.headless",
        "true",
        "--server.port",
        str(os.getenv("STREAMLIT_PORT", 8501)),
    ]
    env = os.environ.copy()
    env.setdefault("BACKEND_URL", os.getenv("BACKEND_URL", "http://localhost:8000"))
    try:
        subprocess.run(streamlit_cmd, check=True, env=env)
    except FileNotFoundError:
        print("Streamlit not installed or not found.")
        sys.exit(1)
    except subprocess.CalledProcessError as err:
        sys.exit(err.returncode)


if __name__ == "__main__":
    main()
