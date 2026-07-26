#!/usr/bin/env python3
import hashlib
import json
import os
import sys
import time
import urllib.error
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
    title = f"Sudoku #{story['sudoku_id']} • {story['displayDate']} ({story['difficulty']})"
    tags = "#thesudokustuff #sudoku #sudokureels #sudokupuzzle #nyt #reels"
    return f"{title}\n\nCan you solve it faster than the breakdown?\n\n{tags}"


def cloudinary_config():
    cloudinary_url = os.getenv("CLOUDINARY_URL", "")
    if cloudinary_url:
        parsed = urllib.parse.urlparse(cloudinary_url)
        return parsed.hostname, parsed.username, parsed.password
    return (
        os.getenv("CLOUDINARY_CLOUD_NAME"),
        os.getenv("CLOUDINARY_API_KEY"),
        os.getenv("CLOUDINARY_API_SECRET"),
    )


def cloudinary_upload(video_path):
    cloud_name, api_key, api_secret = cloudinary_config()
    if not cloud_name or not api_key or not api_secret:
        raise RuntimeError("Cloudinary environment variables missing.")

    timestamp = str(int(time.time()))
    folder = os.getenv("CLOUDINARY_FOLDER", "thesudokustuff")
    public_id = f"sudoku_{timestamp}"
    params_to_sign = f"folder={folder}&public_id={public_id}&timestamp={timestamp}{api_secret}"
    signature = hashlib.sha1(params_to_sign.encode("utf-8")).hexdigest()

    fields = {
        "api_key": api_key,
        "timestamp": timestamp,
        "folder": folder,
        "public_id": public_id,
        "signature": signature,
        "resource_type": "video",
    }
    files = {"file": str(video_path)}

    boundary = f"----thesudokustuff{int(time.time())}"
    chunks = []
    for name, val in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(str(val).encode())
        chunks.append(b"\r\n")
    data_bytes = Path(files["file"]).read_bytes()
    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        f'Content-Disposition: form-data; name="file"; filename="{Path(files["file"]).name}"\r\n'
        "Content-Type: video/mp4\r\n\r\n".encode()
    )
    chunks.append(data_bytes)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"https://api.cloudinary.com/v1_1/{cloud_name}/video/upload",
        data=b"".join(chunks),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["secure_url"], data["public_id"]


def public_video_asset(story):
    public_url = os.getenv("PUBLIC_VIDEO_URL")
    if public_url:
        return public_url, None
    video_url, public_id = cloudinary_upload(VIDEO_PATH)
    return video_url, public_id


def gql_string(value):
    return json.dumps(value)


def create_buffer_post(caption, video_url):
    api_key = require_env("BUFFER_API_KEY")
    channel_id = require_env("BUFFER_INSTAGRAM_CHANNEL_ID")
    mutation = f"""
    mutation {{
      createPost(input: {{
        channelId: {gql_string(channel_id)}
        text: {gql_string(caption)}
        metadata: {{
          instagram: {{
            type: reel
            shouldShareToFeed: true
            isAiGenerated: false
          }}
        }}
        schedulingType: automatic
        mode: addToQueue
        assets: [
          {{
            video: {{
              url: {gql_string(video_url)}
            }}
          }}
        ]
      }}) {{
        ... on PostActionSuccess {{
          post {{ id text }}
        }}
        ... on MutationError {{
          message
        }}
      }}
    }}
    """
    req = urllib.request.Request(
        "https://api.buffer.com/graphql",
        data=json.dumps({"query": mutation}).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Buffer HTTP {exc.code}: {body}") from exc
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    result = data.get("data", {}).get("createPost", {})
    if "message" in result:
        raise RuntimeError(f"Buffer MutationError: {result['message']}")
    return result


def main():
    if QUEUE_FULL_MARKER.exists():
        QUEUE_FULL_MARKER.unlink()

    story = load_story()
    caption = caption_for_story(story)
    print(f"Posting reel to Buffer for Sudoku #{story['sudoku_id']}...")
    video_url, public_id = public_video_asset(story)
    print(f"Uploaded video to Cloudinary: {video_url}")

    result = create_buffer_post(caption, video_url)
    print("SUCCESS: Post added to Buffer Queue!")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
