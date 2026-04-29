from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from fastapi import FastAPI, Request, Response
from azure.servicebus import ServiceBusClient, ServiceBusMessage


app = FastAPI(title="Graph Notification Webhook")

SERVICE_BUS_CONNECTION_STRING = os.getenv("SERVICE_BUS_CONNECTION_STRING", "")
SB_NAMESPACE = os.getenv("SB_NAMESPACE", "")
SB_POLICY = os.getenv("SB_POLICY", "RootManageSharedAccessKey")
SB_KEY = os.getenv("SB_KEY", "")
QUEUE_PREFIX = os.getenv("QUEUE_PREFIX", "ingest-shard-")
SHARD_COUNT = int(os.getenv("SHARD_COUNT", "8"))


def extract_mailbox_id(item: dict[str, Any]) -> str:
    resource = item.get("resource", "") or ""
    if "/users/" in resource and "/messages" in resource:
        try:
            return resource.split("/users/")[1].split("/messages")[0]
        except Exception:
            return "unknown"
    return item.get("mailboxId", "unknown")


def shard_for_mailbox(mailbox_id: str) -> int:
    digest = hashlib.sha256(mailbox_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % SHARD_COUNT


def enqueue_payload(payload: dict[str, Any], queue_name: str) -> None:
    connection = SERVICE_BUS_CONNECTION_STRING
    if not connection and SB_NAMESPACE and SB_KEY:
        connection = (
            f"Endpoint=sb://{SB_NAMESPACE}.servicebus.windows.net/;"
            f"SharedAccessKeyName={SB_POLICY};"
            f"SharedAccessKey={SB_KEY}"
        )

    if not connection:
        raise RuntimeError("Missing SERVICE_BUS_CONNECTION_STRING")

    with ServiceBusClient.from_connection_string(connection) as client:
        with client.get_queue_sender(queue_name=queue_name) as sender:
            sender.send_messages(ServiceBusMessage(json.dumps(payload)))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/graph/notifications")
async def graph_notifications(request: Request) -> Response:
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        return Response(content=validation_token, media_type="text/plain")

    body = await request.json()
    values = body.get("value", [])
    enqueued = 0

    for item in values:
        mailbox_id = extract_mailbox_id(item)
        shard = shard_for_mailbox(mailbox_id)
        queue_name = f"{QUEUE_PREFIX}{shard}"
        payload = {
            "mailboxId": mailbox_id,
            "subscriptionId": item.get("subscriptionId"),
            "resource": item.get("resource"),
            "tenantId": item.get("tenantId"),
            "changeType": item.get("changeType"),
            "clientState": item.get("clientState"),
        }
        enqueue_payload(payload, queue_name)
        enqueued += 1

    return Response(
        content=json.dumps({"received": len(values), "enqueued": enqueued}),
        media_type="application/json",
    )


@app.get("/graph/notifications")
async def graph_notifications_validation(request: Request) -> Response:
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        return Response(content=validation_token, media_type="text/plain")
    return Response(content=json.dumps({"status": "ok"}), media_type="application/json")
