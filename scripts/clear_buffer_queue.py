#!/usr/bin/env python3
import json
import os
import sys
import urllib.request

def gql_string(value):
    return json.dumps(value)

def main():
    api_key = os.getenv("BUFFER_API_KEY")
    channel_id = os.getenv("BUFFER_INSTAGRAM_CHANNEL_ID")
    if not api_key or not channel_id:
        print("Missing BUFFER_API_KEY or BUFFER_INSTAGRAM_CHANNEL_ID env vars.")
        return

    # Query all posts for channel
    query = f"""
    query {{
      channel(id: {gql_string(channel_id)}) {{
        posts {{
          total
          items {{
            id
            status
            text
          }}
        }}
      }}
    }}
    """
    req = urllib.request.Request(
        "https://api.buffer.com/graphql",
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    items = data.get("data", {}).get("channel", {}).get("posts", {}).get("items", [])
    print(f"Found {len(items)} total posts in Buffer channel.")

    for item in items:
        pid = item["id"]
        status = item.get("status")
        print(f"Deleting post {pid} (status: {status})...")
        mutation = f"""
        mutation {{
          deletePost(input: {{ id: {gql_string(pid)} }}) {{
            ... on DeletePostSuccess {{ id }}
            ... on VoidMutationError {{ message }}
          }}
        }}
        """
        req_del = urllib.request.Request(
            "https://api.buffer.com/graphql",
            data=json.dumps({"query": mutation}).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req_del, timeout=60) as rdel:
                d_res = json.loads(rdel.read().decode("utf-8"))
                print(f"Result for {pid}:", d_res.get("data", {}).get("deletePost", {}))
        except Exception as exc:
            print(f"Error deleting post {pid}: {exc}")

if __name__ == "__main__":
    main()
