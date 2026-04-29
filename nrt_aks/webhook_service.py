#!/usr/bin/env python3
"""
Webhook Service - Receives Microsoft Graph change notifications and
publishes them to Azure Event Grid Custom Topic.

Replaces the Azure Service Bus publish step with Event Grid.

Endpoints:
  GET  /health              - Health check
  POST /graph/notifications - Graph change notification receiver
"""

import os
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import PlainTextResponse
from azure.core.credentials import AzureKeyCredential
from azure.eventgrid import EventGridPublisherClient, EventGridEvent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("webhook_service")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GRAPH_CLIENT_STATE = os.environ.get("GRAPH_CLIENT_STATE", "shreyas-nrt-secret")

EVENT_GRID_TOPIC_ENDPOINT = os.environ["EVENT_GRID_TOPIC_ENDPOINT"]
EVENT_GRID_TOPIC_KEY = os.environ["EVENT_GRID_TOPIC_KEY"]

# ---------------------------------------------------------------------------
# Azure Event Grid client
# ---------------------------------------------------------------------------

eg_client = EventGridPublisherClient(
    endpoint=EVENT_GRID_TOPIC_ENDPOINT,
    credential=AzureKeyCredential(EVENT_GRID_TOPIC_KEY),
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Graph Webhook → Event Grid Bridge")


@app.get("/health")
def health():
    return {"status": "ok", "service": "webhook_service"}


@app.post("/graph/notifications")
async def graph_notifications(request: Request):
    """
    Handles two kinds of requests from Microsoft Graph:

    1. Subscription validation (query param ?validationToken=...)
       Graph sends this when you first create a subscription.
       We must echo back the token as plain text with 200.

    2. Change notification (JSON body with 'value' array)
       Graph sends this when a subscribed resource changes.
       We immediately return 202 and publish to Event Grid.
    """
    # --- Subscription validation ---
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        logger.info("Graph subscription validation request received")
        return PlainTextResponse(content=validation_token, status_code=200)

    # --- Change notification ---
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    notifications = body.get("value", [])
    if not notifications:
        logger.warning("Received empty notifications payload")
        return Response(status_code=202)

    published = 0
    for notif in notifications:
        # Validate clientState to prevent spoofing
        if notif.get("clientState") != GRAPH_CLIENT_STATE:
            logger.warning(
                "Rejected notification with mismatched clientState: %s",
                notif.get("clientState"),
            )
            continue

        try:
            _publish_to_event_grid(notif)
            published += 1
        except Exception as exc:
            logger.error("Failed to publish notification to Event Grid: %s", exc)

    logger.info("Processed %d/%d notifications → Event Grid", published, len(notifications))

    # Graph requires 202 Accepted; anything else triggers a retry
    return Response(status_code=202)


# ---------------------------------------------------------------------------
# Helper: publish one Graph notification as an EventGrid event
# ---------------------------------------------------------------------------

def _publish_to_event_grid(notif: Dict[str, Any]) -> None:
    """Publish a Graph change notification as an EventGrid event."""

    # Extract the mailboxId from the resource path.
    # resource looks like: "Users/{userId}/Messages" or "/users/{userId}/mailFolders/inbox/messages"
    resource: str = notif.get("resource", "")
    mailbox_id = _extract_mailbox_id(resource)

    event_data = {
        "mailboxId": mailbox_id,
        "subscriptionId": notif.get("subscriptionId"),
        "changeType": notif.get("changeType"),
        "resource": resource,
        "tenantId": notif.get("tenantId"),
        "clientState": notif.get("clientState"),
        "receivedAt": datetime.now(timezone.utc).isoformat(),
    }

    event = EventGridEvent(
        subject=f"graph/mailbox/{mailbox_id}",
        event_type="Microsoft.Graph.MailboxChanged",
        data=event_data,
        data_version="1.0",
        id=str(uuid.uuid4()),
        event_time=datetime.now(timezone.utc),
    )

    eg_client.send([event])
    logger.info("Published EventGrid event for mailbox %s (change: %s)", mailbox_id, notif.get("changeType"))


def _extract_mailbox_id(resource: str) -> str:
    """Extract user/mailbox ID from a Graph resource path."""
    # e.g. "Users/abc123/Messages" → "abc123"
    # e.g. "/users/abc123/mailFolders/inbox/messages" → "abc123"
    parts = [p for p in resource.replace("\\", "/").split("/") if p]
    for i, part in enumerate(parts):
        if part.lower() in ("users", "user") and i + 1 < len(parts):
            return parts[i + 1]
    # Fallback: return the whole resource as identifier
    return resource or "unknown"


# ---------------------------------------------------------------------------
# Entry point (uvicorn)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
