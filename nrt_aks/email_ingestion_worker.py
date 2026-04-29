#!/usr/bin/env python3
"""
Email Ingestion Worker - Receives Event Grid push events, runs Graph
delta query to fetch new emails, calls OpenAI to extract
{name, email, intent}, then publishes JSON to Azure Event Hubs.

Endpoints:
  GET  /health          - Health check (liveness/readiness probe)
  POST /eventgrid/events - Event Grid push subscription receiver
"""

import os
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import msal
from fastapi import FastAPI, Request, Response, HTTPException
from openai import OpenAI
from azure.eventhub import EventHubProducerClient, EventData
from azure.eventhub.exceptions import EventHubError

from delta_token_store import DeltaTokenStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("email_ingestion_worker")

# ---------------------------------------------------------------------------
# Config (all from environment variables / Kubernetes secrets)
# ---------------------------------------------------------------------------

GRAPH_TENANT_ID = os.environ["GRAPH_TENANT_ID"]
GRAPH_CLIENT_ID = os.environ["GRAPH_CLIENT_ID"]
GRAPH_CLIENT_SECRET = os.environ["GRAPH_CLIENT_SECRET"]

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

EVENTHUB_CONNECTION_STRING = os.environ["EVENTHUB_CONNECTION_STRING"]
EVENTHUB_NAME = os.environ.get("EVENTHUB_NAME", "email-intents")

STORAGE_CONNECTION_STRING = os.environ["STORAGE_CONNECTION_STRING"]

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

openai_client = OpenAI(api_key=OPENAI_API_KEY)

eventhub_producer = EventHubProducerClient.from_connection_string(
    conn_str=EVENTHUB_CONNECTION_STRING,
    eventhub_name=EVENTHUB_NAME,
)

delta_store = DeltaTokenStore(STORAGE_CONNECTION_STRING)

# ---------------------------------------------------------------------------
# MSAL confidential client for Graph API (service principal)
# ---------------------------------------------------------------------------

_msal_app = msal.ConfidentialClientApplication(
    client_id=GRAPH_CLIENT_ID,
    client_credential=GRAPH_CLIENT_SECRET,
    authority=f"https://login.microsoftonline.com/{GRAPH_TENANT_ID}",
)

GRAPH_SCOPES = ["https://graph.microsoft.com/.default"]


def _get_graph_token() -> str:
    result = _msal_app.acquire_token_for_client(scopes=GRAPH_SCOPES)
    if "access_token" not in result:
        raise RuntimeError(f"Failed to acquire Graph token: {result.get('error_description')}")
    return result["access_token"]


# ---------------------------------------------------------------------------
# Graph delta query
# ---------------------------------------------------------------------------

def _strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", " ", text).replace("\n", " ").strip()


def fetch_new_emails(mailbox_id: str) -> List[Dict[str, Any]]:
    """
    Run a delta query for the mailbox. Returns only messages that are
    new since the last run. Stores the updated delta token in blob.
    """
    token = _get_graph_token()
    headers = {"Authorization": f"Bearer {token}"}

    delta_token = delta_store.get(mailbox_id)

    if delta_token:
        # Subsequent call: only fetch changes since last delta token
        url = f"https://graph.microsoft.com/v1.0/users/{mailbox_id}/mailFolders/inbox/messages/delta?$deltaToken={delta_token}"
    else:
        # First call: full initial sync (most recent 10 to keep it bounded)
        url = (
            f"https://graph.microsoft.com/v1.0/users/{mailbox_id}"
            f"/mailFolders/inbox/messages/delta"
            f"?$top=10&$select=id,subject,from,receivedDateTime,bodyPreview,body"
        )

    emails = []
    next_link: Optional[str] = url
    new_delta_token: Optional[str] = None

    with httpx.Client(timeout=30) as client:
        while next_link:
            resp = client.get(next_link, headers=headers)
            if resp.status_code == 410:
                # Delta token expired — reset and do a full sync next time
                logger.warning("Delta token expired for %s, resetting", mailbox_id)
                delta_store.set(mailbox_id, "")
                return []
            resp.raise_for_status()
            page = resp.json()

            for msg in page.get("value", []):
                # Skip tombstone entries (deleted messages)
                if "@removed" in msg:
                    continue
                emails.append(msg)

            # Follow @odata.nextLink pages; stop at @odata.deltaLink
            next_link = page.get("@odata.nextLink")
            if "@odata.deltaLink" in page:
                # Extract token from the deltaLink URL
                delta_link: str = page["@odata.deltaLink"]
                match = re.search(r"[?&]\$deltaToken=([^&]+)", delta_link)
                new_delta_token = match.group(1) if match else delta_link

    if new_delta_token:
        delta_store.set(mailbox_id, new_delta_token)

    logger.info("Delta query for %s → %d new messages", mailbox_id, len(emails))
    return emails


# ---------------------------------------------------------------------------
# OpenAI extraction
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You are an email analysis assistant.
Given an email (subject + body), extract exactly three fields:
1. name   — The full name of the sender (from the body/signature if not obvious from metadata)
2. email  — The sender's email address
3. intent — A single, concise sentence describing the sender's main request or purpose

Respond ONLY with valid JSON in this exact shape, no extra text:
{
  "name": "<full name or null>",
  "email": "<email address or null>",
  "intent": "<one-sentence intent>"
}"""


def extract_with_llm(
    email_id: str,
    subject: str,
    sender_name: str,
    sender_email: str,
    body_text: str,
    received_at: str,
    mailbox_id: str,
) -> Dict[str, Any]:
    """
    Call OpenAI to extract name, email, intent from the email.
    Returns a structured JSON dict ready for Event Hubs.
    """
    user_message = f"""Subject: {subject}
From: {sender_name} <{sender_email}>

Body:
{body_text[:3000]}"""  # Trim to avoid token limits

    try:
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        extracted = json.loads(response.choices[0].message.content)
    except Exception as exc:
        logger.warning("LLM extraction failed for email %s: %s", email_id, exc)
        extracted = {"name": sender_name, "email": sender_email, "intent": "extraction_failed"}

    # Build the canonical output document
    return {
        "event_id": str(uuid.uuid4()),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "email_id": email_id,
        "mailbox_id": mailbox_id,
        "subject": subject,
        "received_at": received_at,
        "sender": {
            "name": extracted.get("name") or sender_name,
            "email": extracted.get("email") or sender_email,
        },
        "intent": extracted.get("intent", ""),
        "model": OPENAI_MODEL,
    }


# ---------------------------------------------------------------------------
# Event Hubs publisher
# ---------------------------------------------------------------------------

def publish_to_eventhubs(payload: Dict[str, Any]) -> None:
    batch = eventhub_producer.create_batch()
    batch.add(EventData(json.dumps(payload)))
    eventhub_producer.send_batch(batch)
    logger.info(
        "Published to Event Hubs: email=%s intent=%r",
        payload.get("email_id"),
        payload.get("intent"),
    )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Email Ingestion Worker")


@app.get("/health")
def health():
    return {"status": "ok", "service": "email_ingestion_worker"}


@app.post("/eventgrid/events")
async def eventgrid_events(request: Request):
    """
    Receives Event Grid push events from the 'Microsoft.Graph.MailboxChanged'
    custom topic subscription.

    Event Grid sends an array of events.
    On first delivery it also sends a SubscriptionValidation handshake.
    """
    body = await request.json()

    # Event Grid sends an array
    events: List[Dict[str, Any]] = body if isinstance(body, list) else [body]

    for event in events:
        event_type = event.get("eventType") or event.get("type", "")

        # --- Subscription validation handshake ---
        if event_type == "Microsoft.EventGrid.SubscriptionValidationEvent":
            code = event.get("data", {}).get("validationCode")
            logger.info("Event Grid subscription validation: code=%s", code)
            return {"validationResponse": code}

        # --- Our custom mail change event ---
        if event_type == "Microsoft.Graph.MailboxChanged":
            data = event.get("data", {})
            mailbox_id = data.get("mailboxId")
            if not mailbox_id:
                logger.warning("Received MailboxChanged event with no mailboxId: %s", event)
                continue
            _process_mailbox(mailbox_id)

    return Response(status_code=200)


def _process_mailbox(mailbox_id: str) -> None:
    """Fetch new emails for a mailbox, extract intents, publish to Event Hubs."""
    try:
        emails = fetch_new_emails(mailbox_id)
    except Exception as exc:
        logger.error("Delta query failed for mailbox %s: %s", mailbox_id, exc)
        return

    for msg in emails:
        email_id = msg.get("id", str(uuid.uuid4()))
        subject = msg.get("subject", "(no subject)")
        sender_obj = msg.get("from", {}).get("emailAddress", {})
        sender_name = sender_obj.get("name", "")
        sender_email = sender_obj.get("address", "")
        received_at = msg.get("receivedDateTime", "")

        body_content = msg.get("body", {}).get("content", "") or msg.get("bodyPreview", "")
        content_type = msg.get("body", {}).get("contentType", "text")
        body_text = _strip_html(body_content) if content_type == "html" else body_content

        payload = extract_with_llm(
            email_id=email_id,
            subject=subject,
            sender_name=sender_name,
            sender_email=sender_email,
            body_text=body_text,
            received_at=received_at,
            mailbox_id=mailbox_id,
        )

        try:
            publish_to_eventhubs(payload)
        except EventHubError as exc:
            logger.error("Event Hubs publish failed for email %s: %s", email_id, exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8081)))
