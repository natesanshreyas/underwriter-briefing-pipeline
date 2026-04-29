from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.ai.textanalytics import TextAnalyticsClient
from azure.servicebus import ServiceBusClient, ServiceBusReceiveMode


SERVICE_BUS_CONNECTION_STRING = os.getenv("SERVICE_BUS_CONNECTION_STRING", "")
SB_NAMESPACE = os.getenv("SB_NAMESPACE", "")
SB_POLICY = os.getenv("SB_POLICY", "RootManageSharedAccessKey")
SB_KEY = os.getenv("SB_KEY", "")
QUEUE_PREFIX = os.getenv("QUEUE_PREFIX", "ingest-shard-")
SHARD_COUNT = int(os.getenv("SHARD_COUNT", "8"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "5"))
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
DEFAULT_LOCAL_SECRETS = Path(__file__).resolve().parents[2] / "secrets.json"
ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from examples_outlook import acquire_interactive_token, get_config


def first_nonempty(*values: str | None, default: str = "") -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return default


def load_local_secrets() -> dict[str, Any]:
    secrets_path = Path(os.getenv("SECRETS_FILE", str(DEFAULT_LOCAL_SECRETS)))
    if not secrets_path.exists():
        return {}
    try:
        with secrets_path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def load_runtime_config() -> dict[str, str]:
    secrets = load_local_secrets()
    return {
        "AZURE_TENANT_ID": first_nonempty(os.getenv("AZURE_TENANT_ID"), secrets.get("AZURE_TENANT_ID")),
        "AZURE_CLIENT_ID": first_nonempty(os.getenv("AZURE_CLIENT_ID"), secrets.get("AZURE_CLIENT_ID")),
        "AZURE_CLIENT_SECRET": first_nonempty(os.getenv("AZURE_CLIENT_SECRET"), secrets.get("AZURE_CLIENT_SECRET")),
        "LANGUAGE_ENDPOINT": first_nonempty(os.getenv("LANGUAGE_ENDPOINT"), secrets.get("LANGUAGE_ENDPOINT")),
        "INTERNAL_DOMAINS": first_nonempty(os.getenv("INTERNAL_DOMAINS"), default=""),
        "DELTA_TOKEN_PATH": first_nonempty(
            os.getenv("DELTA_TOKEN_PATH"),
            default=str(Path(__file__).resolve().parent / ".delta_tokens.json"),
        ),
    }


def get_graph_access_token(config: dict[str, str]) -> str:
    missing = [
        key
        for key in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET")
        if not config.get(key)
    ]
    if missing:
        raise RuntimeError(f"Missing Graph auth settings: {', '.join(missing)}")

    credential = ClientSecretCredential(
        tenant_id=config["AZURE_TENANT_ID"],
        client_id=config["AZURE_CLIENT_ID"],
        client_secret=config["AZURE_CLIENT_SECRET"],
    )
    return credential.get_token(GRAPH_SCOPE).token


def load_delta_tokens(path: str) -> dict[str, str]:
    token_path = Path(path)
    if not token_path.exists():
        return {}
    try:
        with token_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_delta_tokens(path: str, data: dict[str, str]) -> None:
    token_path = Path(path)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with token_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def mailbox_delta_query(resource_prefix: str, token: str, delta_link: str | None) -> tuple[list[dict[str, Any]], str | None]:
    url = delta_link or (
        f"{GRAPH_ROOT}{resource_prefix}/mailFolders/Inbox/messages/delta"
        "?$select=id,subject,from,receivedDateTime,internetMessageId,conversationId,"
        "bodyPreview,hasAttachments,parentFolderId,categories"
    )

    changed: list[dict[str, Any]] = []
    out_delta: str | None = None
    while url:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=30,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Delta query failed ({response.status_code}): {response.text}")

        payload = response.json()
        changed.extend(payload.get("value", []))
        if "@odata.deltaLink" in payload:
            out_delta = payload["@odata.deltaLink"]
        url = payload.get("@odata.nextLink")

    return changed, out_delta


def parse_sender_domain(message: dict[str, Any]) -> str:
    address = (
        message.get("from", {})
        .get("emailAddress", {})
        .get("address", "")
        .strip()
        .lower()
    )
    if "@" not in address:
        return ""
    return address.split("@", 1)[1]


def parse_mailbox_domain(mailbox_id: str) -> str:
    mailbox = (mailbox_id or "").strip().lower()
    if "@" not in mailbox:
        return ""
    return mailbox.split("@", 1)[1]


def is_external_message(message: dict[str, Any], mailbox_id: str, internal_domains: list[str]) -> bool:
    sender_domain = parse_sender_domain(message)
    mailbox_domain = parse_mailbox_domain(mailbox_id)
    if not sender_domain:
        return False
    if mailbox_domain and sender_domain == mailbox_domain:
        return False
    if internal_domains and sender_domain in internal_domains:
        return False
    return True


def build_text_analytics_client(config: dict[str, str]) -> TextAnalyticsClient | None:
    endpoint = config.get("LANGUAGE_ENDPOINT", "").strip()
    if not endpoint:
        return None
    return TextAnalyticsClient(endpoint=endpoint, credential=DefaultAzureCredential())


def analyze_message_content(
    language_client: TextAnalyticsClient | None,
    mailbox_id: str,
    message: dict[str, Any],
) -> dict[str, Any]:
    message_id = message.get("id")
    subject = message.get("subject") or ""
    body_preview = message.get("bodyPreview") or ""
    sender_address = (
        message.get("from", {})
        .get("emailAddress", {})
        .get("address", "")
    )
    payload = {
        "mailboxId": mailbox_id,
        "messageId": message_id,
        "internetMessageId": message.get("internetMessageId"),
        "conversationId": message.get("conversationId"),
        "subject": subject,
        "sender": sender_address,
        "receivedDateTime": message.get("receivedDateTime"),
        "hasAttachments": bool(message.get("hasAttachments", False)),
    }

    if not language_client:
        payload["contentUnderstanding"] = {
            "status": "skipped",
            "reason": "LANGUAGE_ENDPOINT not configured",
        }
        return payload

    text = f"Subject: {subject}\n\n{body_preview}".strip()
    if not text:
        payload["contentUnderstanding"] = {
            "status": "skipped",
            "reason": "No text available",
        }
        return payload

    sentiment_result = language_client.analyze_sentiment(documents=[text])[0]
    key_phrases_result = language_client.extract_key_phrases(documents=[text])[0]
    entities_result = language_client.recognize_entities(documents=[text])[0]

    if sentiment_result.is_error:
        payload["contentUnderstanding"] = {
            "status": "error",
            "message": sentiment_result.error.message,
        }
        return payload

    entity_items: list[dict[str, Any]] = []
    if not entities_result.is_error:
        for entity in entities_result.entities[:10]:
            entity_items.append(
                {
                    "text": entity.text,
                    "category": entity.category,
                    "subCategory": entity.subcategory,
                    "confidenceScore": entity.confidence_score,
                }
            )

    payload["contentUnderstanding"] = {
        "status": "ok",
        "sentiment": {
            "label": sentiment_result.sentiment,
            "confidenceScores": {
                "positive": sentiment_result.confidence_scores.positive,
                "neutral": sentiment_result.confidence_scores.neutral,
                "negative": sentiment_result.confidence_scores.negative,
            },
        },
        "keyPhrases": [] if key_phrases_result.is_error else key_phrases_result.key_phrases[:15],
        "entities": entity_items,
    }
    return payload


def process_mailbox(mailbox_id: str, config: dict[str, str]) -> dict[str, Any]:
    graph_token = get_graph_access_token(config)
    token_path = config["DELTA_TOKEN_PATH"]
    tokens = load_delta_tokens(token_path)
    previous_delta_link = tokens.get(mailbox_id)
    changed_messages, new_delta_link = mailbox_delta_query(f"/users/{mailbox_id}", graph_token, previous_delta_link)

    internal_domains = [d.strip().lower() for d in config.get("INTERNAL_DOMAINS", "").split(",") if d.strip()]
    external_messages = [
        message
        for message in changed_messages
        if is_external_message(message, mailbox_id, internal_domains)
    ]

    language_client = build_text_analytics_client(config)
    analyses = [analyze_message_content(language_client, mailbox_id, message) for message in external_messages]

    if new_delta_link:
        tokens[mailbox_id] = new_delta_link
        save_delta_tokens(token_path, tokens)

    result = {
        "mailboxId": mailbox_id,
        "mode": "application",
        "changedMessageCount": len(changed_messages),
        "externalMessageCount": len(external_messages),
        "deltaLinkUpdated": bool(new_delta_link),
        "items": analyses,
    }
    return result


def graph_get_json(url: str, token: str) -> dict[str, Any]:
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Graph GET failed ({response.status_code}): {response.text}")
    return response.json()


def process_mailbox_delegated(mailbox_id: str | None, config: dict[str, str]) -> dict[str, Any]:
    cfg = get_config()
    client_id = first_nonempty(os.getenv("CLIENT_ID"), cfg.get("CLIENT_ID"))
    if not client_id:
        raise RuntimeError("Missing CLIENT_ID for delegated mode")

    delegated_token = acquire_interactive_token(client_id, scopes=["User.Read", "Mail.Read"])
    if not delegated_token:
        raise RuntimeError("Failed to acquire delegated token")

    me = graph_get_json(f"{GRAPH_ROOT}/me?$select=mail,userPrincipalName,id", delegated_token)
    mailbox_label = mailbox_id or me.get("mail") or me.get("userPrincipalName") or "me"

    token_path = config["DELTA_TOKEN_PATH"]
    tokens = load_delta_tokens(token_path)
    token_key = f"delegated::{mailbox_label}"
    previous_delta_link = tokens.get(token_key)
    changed_messages, new_delta_link = mailbox_delta_query("/me", delegated_token, previous_delta_link)

    internal_domains = [d.strip().lower() for d in config.get("INTERNAL_DOMAINS", "").split(",") if d.strip()]
    external_messages = [
        message
        for message in changed_messages
        if is_external_message(message, mailbox_label, internal_domains)
    ]

    language_client = build_text_analytics_client(config)
    analyses = [analyze_message_content(language_client, mailbox_label, message) for message in external_messages]

    if new_delta_link:
        tokens[token_key] = new_delta_link
        save_delta_tokens(token_path, tokens)

    return {
        "mailboxId": mailbox_label,
        "mode": "delegated",
        "changedMessageCount": len(changed_messages),
        "externalMessageCount": len(external_messages),
        "deltaLinkUpdated": bool(new_delta_link),
        "items": analyses,
    }


def process_payload(payload: dict) -> None:
    mailbox_id = payload.get("mailboxId", "unknown")
    print(
        f"[INGEST] mailbox_id={mailbox_id} subscription_id={payload.get('subscriptionId')} resource={payload.get('resource')}",
        flush=True,
    )

    if mailbox_id == "unknown":
        print("[INGEST] skipped: mailbox_id is unknown", flush=True)
        return

    config = load_runtime_config()
    result = process_mailbox(mailbox_id, config)
    print("[INGEST_JSON] " + json.dumps(result, ensure_ascii=False), flush=True)


def run_forever() -> None:
    connection = SERVICE_BUS_CONNECTION_STRING
    if not connection and SB_NAMESPACE and SB_KEY:
        connection = (
            f"Endpoint=sb://{SB_NAMESPACE}.servicebus.windows.net/;"
            f"SharedAccessKeyName={SB_POLICY};"
            f"SharedAccessKey={SB_KEY}"
        )

    if not connection:
        raise RuntimeError("Missing SERVICE_BUS_CONNECTION_STRING")

    print(f"Worker started. Listening on {SHARD_COUNT} shard queue(s).", flush=True)

    with ServiceBusClient.from_connection_string(connection) as client:
        while True:
            found_messages = 0
            for shard in range(SHARD_COUNT):
                queue_name = f"{QUEUE_PREFIX}{shard}"
                with client.get_queue_receiver(
                    queue_name=queue_name,
                    receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
                    max_wait_time=2,
                ) as receiver:
                    messages = receiver.receive_messages(max_message_count=5, max_wait_time=2)
                    for message in messages:
                        found_messages += 1
                        try:
                            body_text = b"".join([chunk for chunk in message.body]).decode("utf-8")
                            payload = json.loads(body_text)
                            process_payload(payload)
                            receiver.complete_message(message)
                        except Exception as exc:
                            print(f"[ERROR] failed processing message: {exc}", flush=True)
                            receiver.abandon_message(message)

            if found_messages == 0:
                time.sleep(POLL_SECONDS)


def run_once(mailbox_id: str | None, use_delegated: bool) -> None:
    config = load_runtime_config()
    if use_delegated:
        result = process_mailbox_delegated(mailbox_id, config)
    else:
        if not mailbox_id:
            raise RuntimeError("--mailbox-id is required in application mode")
        result = process_mailbox(mailbox_id, config)
    print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Service Bus worker with Graph delta + content understanding")
    parser.add_argument("--mailbox-id", help="Run a one-shot delta query for a mailbox ID or UPN")
    parser.add_argument("--use-delegated", action="store_true", help="Use delegated /me token flow for local testing")
    args = parser.parse_args()
    if args.mailbox_id or args.use_delegated:
        run_once(args.mailbox_id, args.use_delegated)
    else:
        run_forever()
