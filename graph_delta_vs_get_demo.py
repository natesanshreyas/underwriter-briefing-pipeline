#!/usr/bin/env python3
"""
Demo: GET per notification vs Delta reconciliation on the repo mailbox (/me).

Uses the same delegated auth flow as examples_outlook.py (device code).
Stores the delta link in .graph_delta_token.json for repeat runs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from examples_outlook import acquire_interactive_token, get_config

DELTA_TOKEN_PATH = Path(".graph_delta_token.json")
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


def graph_get(url: str, access_token: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Graph API error {response.status_code}: {response.text}")
    return response.json()


def graph_post(url: str, access_token: str, payload: Dict[str, Any]) -> None:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code not in (200, 202):
        raise RuntimeError(f"Graph API error {response.status_code}: {response.text}")


def load_delta_link() -> Optional[str]:
    if not DELTA_TOKEN_PATH.exists():
        return None
    try:
        data = json.loads(DELTA_TOKEN_PATH.read_text(encoding="utf-8"))
        return data.get("deltaLink")
    except Exception:
        return None


def save_delta_link(delta_link: str) -> None:
    DELTA_TOKEN_PATH.write_text(
        json.dumps({"deltaLink": delta_link}, indent=2),
        encoding="utf-8",
    )


def get_latest_message(access_token: str) -> Optional[Dict[str, Any]]:
    url = (
        f"{GRAPH_ROOT}/me/messages?"
        "$top=1&$select=id,subject,receivedDateTime,from"
        "&$orderby=receivedDateTime desc"
    )
    payload = graph_get(url, access_token)
    values = payload.get("value", [])
    return values[0] if values else None


def get_me_address(access_token: str) -> str:
    url = f"{GRAPH_ROOT}/me?$select=mail,userPrincipalName"
    payload = graph_get(url, access_token)
    return payload.get("mail") or payload.get("userPrincipalName") or ""


def send_test_email(access_token: str, subject: str, body_text: str) -> None:
    to_address = get_me_address(access_token)
    if not to_address:
        raise RuntimeError("Unable to determine mailbox address for /me.")

    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body_text,
            },
            "toRecipients": [
                {"emailAddress": {"address": to_address}},
            ],
        },
        "saveToSentItems": True,
    }
    graph_post(f"{GRAPH_ROOT}/me/sendMail", access_token, payload)
    print(f"Sent test email to {to_address}")


def demo_get_per_notification(access_token: str) -> None:
    print("=== Demo A: Push -> GET per notification ===")
    latest = get_latest_message(access_token)
    if not latest:
        print("No messages found in mailbox.")
        return

    message_id = latest.get("id")
    if not message_id:
        print("Latest message missing ID.")
        return

    url = f"{GRAPH_ROOT}/me/messages/{message_id}?$select=id,subject,receivedDateTime,from"
    message = graph_get(url, access_token)

    sender = (message.get("from") or {}).get("emailAddress", {}).get("address", "unknown")
    print("Notification message ID:", message_id)
    print("GET returned:")
    print(f"  Subject: {message.get('subject')}")
    print(f"  From: {sender}")
    print(f"  Received: {message.get('receivedDateTime')}")


def demo_delta_reconcile(access_token: str) -> None:
    print("\n=== Demo B: Push -> Delta reconcile ===")
    delta_link = load_delta_link()

    if delta_link:
        print("Using stored delta link.")
        url = delta_link
    else:
        print("No delta link found. Starting initial delta query...")
        url = (
            f"{GRAPH_ROOT}/me/mailFolders/Inbox/messages/delta"
            "?$select=id,subject,receivedDateTime,from"
            "&$top=5"
        )

    changes: List[Dict[str, Any]] = []
    next_link = url
    delta_link_out: Optional[str] = None

    # Read up to 2 pages to keep the demo short
    for _ in range(2):
        payload = graph_get(next_link, access_token)
        changes.extend(payload.get("value", []))
        if "@odata.deltaLink" in payload:
            delta_link_out = payload["@odata.deltaLink"]
            break
        next_link = payload.get("@odata.nextLink")
        if not next_link:
            break

    if delta_link_out:
        save_delta_link(delta_link_out)
        print("Stored new delta link.")

    print(f"Delta returned {len(changes)} change(s).")
    for msg in changes[:5]:
        sender = (msg.get("from") or {}).get("emailAddress", {}).get("address", "unknown")
        print(f"  - {msg.get('subject')} | {sender} | {msg.get('receivedDateTime')}")


def main() -> None:
    cfg = get_config()
    client_id = cfg.get("CLIENT_ID")
    if not client_id:
        raise SystemExit("Missing CLIENT_ID in env or secrets.json")

    base_scopes = ["Mail.Read", "User.Read"]
    send_enabled = os.getenv("SEND_TEST_EMAIL", "0") == "1"
    scopes = base_scopes + (["Mail.Send"] if send_enabled else [])

    token = acquire_interactive_token(client_id, scopes=scopes)
    if not token:
        raise SystemExit("Failed to acquire token")

    if send_enabled:
        send_test_email(
            token,
            subject="Delta Demo: Test Email",
            body_text="This is a demo email to show delta reconciliation.",
        )

    demo_get_per_notification(token)
    demo_delta_reconcile(token)


if __name__ == "__main__":
    main()
