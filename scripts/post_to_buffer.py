#!/usr/bin/env python3
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIDEO_PATH = ROOT / "outputs" / "thesudokustuff_mvp.mp4"
STORY_PATH = ROOT / "outputs" / "thesudokustuff_storyboard.json"
QUEUE_FULL_MARKER = ROOT / "outputs" / "queue_full"

def require_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value

def load_story():
    return json.loads(STORY_PATH.read_text(encoding="utf-8"))

def caption_for_story(story):
    title = f"Sudoku #{story['sudoku_id']} - {story['displayDate']} ({story['difficulty']})"
    tags = "#thesudokustuff #sudoku #sudokureels #sudokupuzzle #nyt #reels"
    return f"{title}\n\nCan you solve it faster than the breakdown?\n\n{tags}"

def multipart_body(fields, files):
    boundary = f"----thesudokustuff{int(time.time())}"
    chunks = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(str(value).encode())
        chunks.append(b"\r\n")
    for name, path in files.items():
        data = Path(path).read_bytes()
        chunks.append(f"--{boundary}\r\n".encode())
        header = (
            f'Content-Disposition: form-data; name="{name}"; filename="{Path(path).name}"\r\n'
            "Content-Type: video/mp4\r\n\r\n"
        )
        chunks.append(header.encode())
        chunks.append(data)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return boundary, b"".join(chunks)

def cloudinary_config():
    cloudinary_url = os.getenv("CLOUDINARY_URL", "")
    if cloudinary_url:
        parsed = urllib.parse.urlparse(cloudinary_url)
        return parsed.hostname, parsed.username, parsed.password
    return os.getenv("CLOUDINARY_CLOUD_NAME"), os.getenv("CLOUDINARY_API_KEY"), os.getenv("CLOUDINARY_API_SECRET")

def cloudinary_upload(video_path):
    cloud_name, api_key, api_secret = cloudinary_config()
    if not cloud_name or not api_key or not api_secret:
        raise RuntimeError("Set PUBLIC_VIDEO_URL or Cloudinary env vars for public MP4 hosting.")

    timestamp = str(int(time.time()))
    public_id = f"thesudokustuff/{timestamp}"
    params = {"public_id": public_id, "timestamp": timestamp, "overwrite": "true"}
    signature_base = "&".join(f"{key}={params[key]}" for key in sorted(params))
    signature = hashlib.sha1(f"{signature_base}{api_secret}".encode()).hexdigest()
    fields = {**params, "api_key": api_key, "signature": signature}
    boundary, body = multipart_body(fields, {"file": video_path})
    req = urllib.request.Request(
        f"https://api.cloudinary.com/v1_1/{cloud_name}/video/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["secure_url"], data.get("public_id", public_id)

def cloudinary_destroy(public_id):
    cloud_name, api_key, api_secret = cloudinary_config()
    if not cloud_name or not api_key or not api_secret or not public_id:
        return
    timestamp = str(int(time.time()))
    signature_base = f"public_id={public_id}&timestamp={timestamp}{api_secret}"
    signature = hashlib.sha1(signature_base.encode()).hexdigest()
    body = urllib.parse.urlencode(
        {
            "public_id": public_id,
            "timestamp": timestamp,
            "api_key": api_key,
            "signature": signature,
        }
    ).encode()
    req = urllib.request.Request(
        f"https://api.cloudinary.com/v1_1/{cloud_name}/video/destroy",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            pass
    except Exception:
        pass

def buffer_get(token, endpoint):
    url = f"https://api.bufferapp.com/1/{endpoint}.json?access_token={token}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

def get_channel_queue_count(token, channel_id):
    data = buffer_get(token, f"profiles/{channel_id}/updates/pending")
    if isinstance(data, dict) and "total" in data:
        return int(data["total"])
    if isinstance(data, dict) and "updates" in data:
        return len(data["updates"])
    return 0

def post_to_buffer(token, channel_id, text, video_url):
    url = f"https://api.bufferapp.com/1/profiles/{channel_id}/updates/create.json"
    fields = [
        ("access_token", token),
        ("text", text),
        ("profile_ids[]", channel_id),
        ("media[link]", video_url),
        ("media[video]", video_url),
    ]
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))

def main():
    if not VIDEO_PATH.exists():
        raise RuntimeError(f"Video file missing: {VIDEO_PATH}")
    if not STORY_PATH.exists():
        raise RuntimeError(f"Storyboard missing: {STORY_PATH}")

    token = require_env("BUFFER_API_KEY")
    channel_id = os.getenv("BUFFER_INSTAGRAM_CHANNEL_ID") or os.getenv("BUFFER_PROFILE_ID")
    if not channel_id:
        raise RuntimeError("Missing BUFFER_INSTAGRAM_CHANNEL_ID or BUFFER_PROFILE_ID")

    max_queue = int(os.getenv("MAX_BUFFER_QUEUE", "5"))
    queue_count = get_channel_queue_count(token, channel_id)
    print(f"Current Buffer queue count: {queue_count} (max target: {max_queue})")

    if queue_count >= max_queue:
        print("Buffer queue is sufficiently full. Skipping post for this run.")
        QUEUE_FULL_MARKER.write_text(f"queue_count={queue_count}\n", encoding="utf-8")
        return

    QUEUE_FULL_MARKER.unlink(missing_ok=True)
    story = load_story()
    caption = caption_for_story(story)
    video_url = os.getenv("PUBLIC_VIDEO_URL")
    public_id = None

    if not video_url:
        print("Uploading generated reel to Cloudinary...")
        video_url, public_id = cloudinary_upload(VIDEO_PATH)
        print(f"Cloudinary video URL: {video_url}")

    print("Posting update to Buffer...")
    res = post_to_buffer(token, channel_id, caption, video_url)
    print(f"Buffer API response: {json.dumps(res, indent=2)}")

    if public_id:
        print(f"Cleaning up temporary Cloudinary upload: {public_id}")
        cloudinary_destroy(public_id)

if __name__ == "__main__":
    main()
