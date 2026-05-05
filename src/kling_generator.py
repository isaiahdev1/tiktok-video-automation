"""Generate AI video clips via Kling AI API (set KLING_ACCESS_KEY + KLING_SECRET_KEY)."""
from __future__ import annotations
import os
import time
import hmac
import hashlib
import base64
import json
import requests


KLING_BASE = "https://api.klingai.com"


def generate_kling_clips(prompts: list[str], output_dir: str) -> list[str]:
    access_key = os.environ.get("KLING_ACCESS_KEY", "")
    secret_key = os.environ.get("KLING_SECRET_KEY", "")
    if not access_key or not secret_key:
        print("[kling] KLING_ACCESS_KEY / KLING_SECRET_KEY not set — skipping.")
        return []

    os.makedirs(output_dir, exist_ok=True)
    headers = {
        "Authorization": f"Bearer {_jwt(access_key, secret_key)}",
        "Content-Type": "application/json",
    }

    task_ids: list[tuple[int, str]] = []
    for i, prompt in enumerate(prompts):
        try:
            resp = requests.post(
                f"{KLING_BASE}/v1/videos/text2video",
                headers=headers,
                json={
                    "model_name": "kling-v1-6",
                    "prompt": prompt + ", cinematic vertical 9:16, photorealistic, 4k",
                    "aspect_ratio": "9:16",
                    "duration": "5",
                    "cfg_scale": 0.5,
                },
                timeout=30,
            )
            resp.raise_for_status()
            task_id = resp.json()["data"]["task_id"]
            task_ids.append((i, task_id))
            print(f"[kling] Queued {i + 1}/{len(prompts)}: {task_id}")
        except Exception as e:
            print(f"[kling] Failed to queue clip {i}: {e}")
        time.sleep(1)

    paths = []
    for i, task_id in task_ids:
        path = _poll(task_id, i, output_dir, access_key, secret_key)
        if path:
            paths.append(path)

    return paths


# ── helpers ───────────────────────────────────────────────────────────────────

def _jwt(access_key: str, secret_key: str) -> str:
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    now = int(time.time())
    payload = base64.urlsafe_b64encode(
        json.dumps({"iss": access_key, "exp": now + 1800, "nbf": now - 5}).encode()
    ).rstrip(b"=").decode()
    msg = f"{header}.{payload}".encode()
    sig = base64.urlsafe_b64encode(
        hmac.new(secret_key.encode(), msg, digestmod=hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.{sig}"


def _poll(task_id: str, index: int, output_dir: str, ak: str, sk: str) -> str | None:
    headers = {"Authorization": f"Bearer {_jwt(ak, sk)}"}
    for _ in range(72):  # up to 6 min
        time.sleep(5)
        try:
            resp = requests.get(
                f"{KLING_BASE}/v1/videos/text2video/{task_id}",
                headers=headers,
                timeout=15,
            )
            data = resp.json().get("data", {})
            status = data.get("task_status", "")
            if status == "succeed":
                url = data["task_result"]["videos"][0]["url"]
                path = os.path.join(output_dir, f"kling_{index:02d}.mp4")
                r = requests.get(url, timeout=120)
                with open(path, "wb") as f:
                    f.write(r.content)
                print(f"[kling] {index + 1} downloaded")
                return path
            elif status == "failed":
                print(f"[kling] Clip {index} failed: {data.get('task_status_msg', '')}")
                return None
        except Exception as e:
            print(f"[kling] Poll error on {task_id}: {e}")
    print(f"[kling] Timed out on clip {index}")
    return None
