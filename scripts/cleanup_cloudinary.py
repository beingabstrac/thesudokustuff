#!/usr/bin/env python3
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

def cloudinary_config():
    cloudinary_url = os.getenv("CLOUDINARY_URL", "")
    if cloudinary_url:
        parsed = urllib.parse.urlparse(cloudinary_url)
        return parsed.hostname, parsed.username, parsed.password
    return os.getenv("CLOUDINARY_CLOUD_NAME"), os.getenv("CLOUDINARY_API_KEY"), os.getenv("CLOUDINARY_API_SECRET")

def list_and_delete_old_videos(cloud_name, api_key, api_secret, prefix="thesudokustuff/", max_age_hours=2):
    auth = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
    params = urllib.parse.urlencode({"prefix": prefix, "max_results": "100"})
    req = urllib.request.Request(
        f"https://api.cloudinary.com/v1_1/{cloud_name}/resources/video/upload?{params}",
        headers={"Authorization": f"Basic {auth}"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    
    resources = data.get("resources", [])
    now = time.time()
    deleted = []
    
    for item in resources:
        created_at_str = item.get("created_at") # ISO format or timestamp
        public_id = item.get("public_id")
        # Extract timestamp from public_id if formatted as thesudokustuff/1700000000
        try:
            parts = public_id.split("/")
            if len(parts) > 1 and parts[1].isdigit():
                created_ts = int(parts[1])
                age_hours = (now - created_ts) / 3600
                if age_hours >= max_age_hours:
                    delete_resource(cloud_name, api_key, api_secret, public_id)
                    deleted.append(public_id)
        except Exception as exc:
            print(f"Error checking {public_id}: {exc}", file=sys.stderr)
            
    print(json.dumps({"deleted": deleted, "total_checked": len(resources)}, indent=2))

def delete_resource(cloud_name, api_key, api_secret, public_id):
    timestamp = str(int(time.time()))
    signature_base = f"public_id={public_id}&timestamp={timestamp}{api_secret}"
    signature = hashlib.sha1(signature_base.encode()).hexdigest()
    body = urllib.parse.urlencode({
        "public_id": public_id,
        "timestamp": timestamp,
        "api_key": api_key,
        "signature": signature
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.cloudinary.com/v1_1/{cloud_name}/video/destroy",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        resp.read()

def main():
    cloud_name, api_key, api_secret = cloudinary_config()
    if not (cloud_name and api_key and api_secret):
        print("Cloudinary credentials not configured, skipping cleanup.")
        return
    list_and_delete_old_videos(cloud_name, api_key, api_secret)

if __name__ == "__main__":
    main()
