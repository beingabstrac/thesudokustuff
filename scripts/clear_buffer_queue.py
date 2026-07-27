#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

def gql_string(value):
    return json.dumps(value)

def clear_via_rest(token, channel_id):
    print(f"Checking Buffer REST v1 API for channel {channel_id}...")
    url = f"https://api.bufferapp.com/1/profiles/{channel_id}/updates/pending.json?access_token={token}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            updates = data.get("updates", [])
            print(f"REST API found {len(updates)} pending updates.")
            for u in updates:
                uid = u["id"]
                del_url = f"https://api.bufferapp.com/1/updates/destroy/{uid}.json?access_token={token}"
                d_req = urllib.request.Request(del_url, data=b"", headers={"Content-Type": "application/x-www-form-urlencoded"})
                with urllib.request.urlopen(d_req, timeout=30) as d_resp:
                    print(f"Deleted REST update {uid}: {d_resp.read().decode('utf-8')}")
    except Exception as exc:
        print(f"REST v1 clear notice: {exc}")

def clear_via_graphql(token, channel_id):
    print(f"Checking Buffer GraphQL API for channel {channel_id}...")
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
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        items = data.get("data", {}).get("channel", {}).get("posts", {}).get("items", [])
        print(f"GraphQL API found {len(items)} posts.")

        for item in items:
            pid = item["id"]
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
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req_del, timeout=60) as rdel:
                d_res = json.loads(rdel.read().decode("utf-8"))
                print(f"Deleted GraphQL post {pid}:", d_res.get("data", {}).get("deletePost", {}))
    except Exception as exc:
        print(f"GraphQL clear notice: {exc}")

def main():
    token = os.getenv("BUFFER_API_KEY")
    channel_id = os.getenv("BUFFER_INSTAGRAM_CHANNEL_ID")
    if not token or not channel_id:
        print("Missing BUFFER_API_KEY or BUFFER_INSTAGRAM_CHANNEL_ID env vars.")
        return

    clear_via_rest(token, channel_id)
    clear_via_graphql(token, channel_id)

if __name__ == "__main__":
    main()
