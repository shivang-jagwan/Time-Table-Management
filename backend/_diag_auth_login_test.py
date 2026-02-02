from __future__ import annotations

import os

import requests


def main() -> None:
    base = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
    username = os.environ.get("USERNAME", "graphicerahill")
    password = os.environ.get("PASSWORD", "Graphic@ERA123")

    s = requests.Session()

    r = s.post(f"{base}/api/auth/login", json={"username": username, "password": password})
    print("login", r.status_code, r.text)

    r2 = s.get(f"{base}/api/auth/me")
    print("me", r2.status_code, r2.text)


if __name__ == "__main__":
    main()
