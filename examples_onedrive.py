#!/usr/bin/env python3
"""
List OneDrive root files for a PERSONAL Microsoft account (consumer OneDrive)
using device code flow and MSAL.

Prereqs:
  - Entra App Registration
      Supported account types:
        "Accounts in any organizational directory and personal Microsoft accounts"
        OR "All Microsoft account users"
  - Delegated Microsoft Graph permission:
        Files.Read
        (User.Read optional)

Install:
  pip install msal requests

Run:
  export CLIENT_ID=your-client-id
  python examples_onedrive.py

Or create secrets.json:
{
  "CLIENT_ID": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
"""

from __future__ import annotations
import json
import os
import sys
from typing import Optional

import requests
from msal import PublicClientApplication

SECRETS_FILE = "secrets.json"


# -------------------------
# Config loading
# -------------------------

def load_secrets_from_file(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        print(f"Failed to read {path}: {exc}")
        return {}


def get_config() -> dict:
    cfg = {
        "CLIENT_ID": os.getenv("CLIENT_ID"),
    }

    if not cfg["CLIENT_ID"]:
        local = load_secrets_from_file(SECRETS_FILE)
        cfg["CLIENT_ID"] = local.get("CLIENT_ID")

    return cfg


# -------------------------
# Auth
# -------------------------

def acquire_device_flow_token_consumer(client_id: str) -> Optional[str]:
    app = PublicClientApplication(
        client_id=client_id,
        authority="https://login.microsoftonline.com/consumers",
    )

    scopes = ["Files.Read", "User.Read"]

    print("\n--- Device Flow Authentication (Personal Microsoft Account) ---\n")
    flow = app.initiate_device_flow(scopes=scopes)

    if "user_code" not in flow:
        print("Failed to start device flow:", flow)
        return None

    print(f"Device Code: {flow['user_code']}")
    print(f"URL: {flow['verification_uri']}")
    print("\nSign in with the Microsoft account that owns your OneDrive.\n")

    token = app.acquire_token_by_device_flow(flow)

    if "access_token" not in token:
        print("Token acquisition failed:")
        print(json.dumps(token, indent=2))
        return None

    return token["access_token"]


# -------------------------
# Graph helpers
# -------------------------

def graph_get(access_token: str, url: str) -> requests.Response:
    headers = {"Authorization": f"Bearer {access_token}"}
    return requests.get(url, headers=headers, timeout=30)


def whoami(access_token: str) -> None:
    r = graph_get(access_token, "https://graph.microsoft.com/v1.0/me")

    if r.status_code != 200:
        print("Graph /me error:", r.status_code, r.text)
        return

    me = r.json()
    print("\n--- Signed in as ---")
    print("displayName:", me.get("displayName"))
    print("userPrincipalName:", me.get("userPrincipalName"))
    print("id:", me.get("id"))
    print("--------------------\n")


def list_drive_root_children(access_token: str) -> None:
    url = "https://graph.microsoft.com/v1.0/me/drive/root/children"
    r = graph_get(access_token, url)

    if r.status_code != 200:
        print("Graph API error:", r.status_code, r.text)
        return

    items = r.json().get("value", [])

    if not items:
        print("Drive root is empty.")
        return

    print("--- OneDrive root items ---")
    for item in items:
        kind = "folder" if "folder" in item else "file"
        print(f"{kind:6}  {item.get('name')}  (id={item.get('id')})")
    print("---------------------------")


# -------------------------
# Main
# -------------------------

def main() -> None:
    cfg = get_config()

    if not cfg.get("CLIENT_ID"):
        print("Missing CLIENT_ID. Set env var or secrets.json.")
        sys.exit(1)

    token = acquire_device_flow_token_consumer(cfg["CLIENT_ID"])
    if not token:
        sys.exit(1)

    whoami(token)
    list_drive_root_children(token)


if __name__ == "__main__":
    main()
