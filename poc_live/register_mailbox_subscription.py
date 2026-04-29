#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples_outlook import acquire_interactive_token, get_config


GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
DEFAULT_WEBHOOK = "https://webhook-live-shreyas2.wittycoast-8279cbed.eastus.azurecontainerapps.io/graph/notifications"


def graph_get(token: str, url: str) -> dict:
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"GET failed {response.status_code}: {response.text}")
    return response.json()


def graph_post(token: str, url: str, payload: dict) -> dict:
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if response.status_code not in (200, 201, 202):
        raise RuntimeError(f"POST failed {response.status_code}: {response.text}")
    if response.text:
        return response.json()
    return {}


def create_subscription(token: str, webhook_url: str) -> dict:
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=55)).isoformat().replace("+00:00", "Z")
    payload = {
        "changeType": "created",
        "notificationUrl": webhook_url,
        "resource": "/me/messages",
        "expirationDateTime": expiry,
        "clientState": "mailnrt-demo-state",
    }
    return graph_post(token, f"{GRAPH_ROOT}/subscriptions", payload)


def list_subscriptions(token: str) -> list[dict]:
    data = graph_get(token, f"{GRAPH_ROOT}/subscriptions")
    return data.get("value", [])


def send_test_email(token: str) -> None:
    me = graph_get(token, f"{GRAPH_ROOT}/me?$select=mail,userPrincipalName")
    to_address = me.get("mail") or me.get("userPrincipalName")
    if not to_address:
        raise RuntimeError("Could not determine mailbox address for /me")

    payload = {
        "message": {
            "subject": "NRT subscription test email",
            "body": {
                "contentType": "Text",
                "content": "This is a test email to validate Graph subscription -> webhook -> ingestion flow.",
            },
            "toRecipients": [{"emailAddress": {"address": to_address}}],
        },
        "saveToSentItems": True,
    }
    graph_post(token, f"{GRAPH_ROOT}/me/sendMail", payload)
    print(f"Sent test email to {to_address}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create/list Graph mailbox subscription and send test email.")
    parser.add_argument("--webhook-url", default=DEFAULT_WEBHOOK)
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--send-test", action="store_true")
    args = parser.parse_args()

    cfg = get_config()
    client_id = cfg.get("CLIENT_ID")
    if not client_id:
        raise SystemExit("Missing CLIENT_ID in environment or secrets.json")

    scopes = ["User.Read", "Mail.Read", "Mail.Send"]
    token = acquire_interactive_token(client_id, scopes=scopes)
    if not token:
        raise SystemExit("Failed to get Graph token")

    if args.create:
        created = create_subscription(token, args.webhook_url)
        print("Created subscription:")
        print(json.dumps(created, indent=2))

    if args.list:
        subs = list_subscriptions(token)
        print("Current subscriptions:")
        print(json.dumps(subs, indent=2))

    if args.send_test:
        send_test_email(token)


if __name__ == "__main__":
    main()
