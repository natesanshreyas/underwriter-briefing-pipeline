#!/usr/bin/env python3
"""
Device flow example to list your Outlook emails.

Uses delegated permissions - you sign in interactively (device code),
and the script accesses your Outlook inbox.

Prereqs:
 - App registration with Delegated permission Mail.Read.
 - "Allow public client flows" enabled in Authentication.

Install dependencies:
    pip install -r requirements.txt

Run:
    python examples_outlook.py
"""
from __future__ import annotations

import atexit
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import requests
from azure.ai.textanalytics import TextAnalyticsClient
from azure.identity import DefaultAzureCredential
from msal import PublicClientApplication, SerializableTokenCache


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
        "LANGUAGE_ENDPOINT": os.getenv("LANGUAGE_ENDPOINT"),
    }

    if not cfg["CLIENT_ID"] or not cfg["LANGUAGE_ENDPOINT"]:
        local = load_secrets_from_file("secrets.json")
        if not cfg["CLIENT_ID"]:
            cfg["CLIENT_ID"] = local.get("CLIENT_ID")
        if not cfg["LANGUAGE_ENDPOINT"]:
            cfg["LANGUAGE_ENDPOINT"] = local.get("LANGUAGE_ENDPOINT")

    return cfg


def get_token_cache(cache_path: Path) -> SerializableTokenCache:
    cache = SerializableTokenCache()
    if cache_path.exists():
        cache.deserialize(cache_path.read_text(encoding="utf-8"))

    def _save_cache() -> None:
        if cache.has_state_changed:
            cache_path.write_text(cache.serialize(), encoding="utf-8")

    atexit.register(_save_cache)
    return cache


def get_textanalytics_client(endpoint: str) -> TextAnalyticsClient:
    return TextAnalyticsClient(endpoint=endpoint, credential=DefaultAzureCredential())


def strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", " ", text).replace("\n", " ").strip()


def summarize_broker_entities(entities: list) -> dict:
    summary = {
        "people": [],
        "organizations": [],
        "emails": [],
        "phones": [],
        "urls": [],
        "addresses": [],
        "other": [],
    }

    if not entities:
        return summary

    for ent in entities:
        category = (ent.category or "").lower()
        text = ent.text
        if category == "person":
            summary["people"].append(text)
        elif category == "organization":
            summary["organizations"].append(text)
        elif category == "email":
            summary["emails"].append(text)
        elif category == "phonenumber":
            summary["phones"].append(text)
        elif category == "url":
            summary["urls"].append(text)
        elif category == "address":
            summary["addresses"].append(text)
        else:
            summary["other"].append({"text": text, "category": ent.category})

    # De-duplicate while preserving order
    for key, values in summary.items():
        if key == "other":
            continue
        seen = set()
        deduped = []
        for v in values:
            if v not in seen:
                seen.add(v)
                deduped.append(v)
        summary[key] = deduped

    return summary


def assess_broker(broker_name: str, body_text: str, entities: list) -> dict:
    name_norm = broker_name.strip().lower()
    mention_count = len(re.findall(rf"\b{re.escape(name_norm)}\b", body_text.lower()))
    person_mentions = [
        ent for ent in entities
        if (ent.category or "").lower() == "person" and ent.text.strip().lower() == name_norm
    ]
    confidence = (
        sum(ent.confidence_score for ent in person_mentions) / len(person_mentions)
        if person_mentions
        else None
    )
    broker_meta = summarize_broker_entities(entities)
    return {
        "mentioned": mention_count > 0,
        "mention_count": mention_count,
        "confidence": confidence,
        "organizations": broker_meta["organizations"],
        "emails": broker_meta["emails"],
        "phones": broker_meta["phones"],
        "urls": broker_meta["urls"],
        "addresses": broker_meta["addresses"],
    }

def acquire_interactive_token(client_id: str, scopes: Optional[list] = None) -> Optional[str]:
    cache_path = Path(".msal_cache.json")
    cache = get_token_cache(cache_path)
    app = PublicClientApplication(
        client_id,
        authority="https://login.microsoftonline.com/consumers",
        token_cache=cache,
    )
    scopes = scopes or ["Mail.Read", "User.Read"]

    accounts = app.get_accounts()
    if accounts:
        token = app.acquire_token_silent(scopes=scopes, account=accounts[0])
        if token and "access_token" in token:
            print("✓ Using cached token")
            return token["access_token"]

    print("\n--- Device Flow Authentication ---\n")
    flow = app.initiate_device_flow(scopes=scopes)
    if "device_code" not in flow or "user_code" not in flow:
        print("Failed to start device flow. Response:")
        print(json.dumps(flow, indent=2))
        print("\nMake sure this app allows public client flows in Azure Authentication settings.")
        return None

    print(f"Device Code: {flow.get('user_code')}")
    print(f"URL: {flow.get('verification_uri')}")
    print("\nOpen the URL in your browser, enter the code, and sign in.\n")

    token = app.acquire_token_by_device_flow(flow)
    if "access_token" not in token:
        print("Failed to acquire token:", token)
        return None

    print("✓ Token acquired successfully")
    return token["access_token"]


def list_inbox_messages(access_token: str, language_endpoint: str) -> None:
    headers = {"Authorization": f"Bearer {access_token}"}

    # First, test if the token works at all by calling /me
    print("Testing token with /me endpoint...")
    r = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)
    if r.status_code == 200:
        user = r.json()
        print(f"✓ Authenticated as: {user.get('userPrincipalName', 'Unknown')}\n")
    else:
        print(f"✗ Failed to call /me: {r.status_code}")
        print(f"Response: {r.text}")
        return

    # Now try to get messages
    print("Fetching inbox messages...")
    url = "https://graph.microsoft.com/v1.0/me/messages?$top=2&$select=subject,from,receivedDateTime,body"
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(f"Graph API error: {r.status_code}")
        print(f"Response: {r.text}")
        print("\nThis might mean your tenant doesn't have Exchange/Outlook provisioned.")
        return
    payload = r.json()
    messages = payload.get("value", [])
    if not messages:
        print("No messages found in your inbox.")
        return

    print(f"\nFound {len(messages)} recent message(s):\n")
    broker_profiles = {}  # Key: sender email, Value: aggregated data
    for msg in messages:
        subject = msg.get("subject", "(No subject)")
        sender = msg.get("from", {}).get("emailAddress", {}).get("address", "Unknown")
        received = msg.get("receivedDateTime", "Unknown")
        body = msg.get("body", {})
        body_content = body.get("content", "")
        content_type = body.get("contentType", "text")
        body_text = strip_html(body_content) if content_type.lower() == "html" else body_content
        print(f"From: {sender}")
        print(f"Subject: {subject}")
        print(f"Received: {received}")
        print(f"\nEmail Body:\n{body_text}\n")
        print("-" * 60)

        # Initialize broker profile if needed
        if sender not in broker_profiles:
            broker_profiles[sender] = {
                "emails": [],
                "sentiments": [],
                "companies": set(),
                "contacts": set(),
                "contact_emails": set(),
            }

        broker_profiles[sender]["emails"].append(subject)

        if language_endpoint:
            client = get_textanalytics_client(language_endpoint)
            response = client.analyze_sentiment(documents=[body_text])
            result = response[0]
            if result.is_error:
                print("Sentiment analysis error:", result)
            else:
                print("Sentiment:", result.sentiment)
                print("Scores:", result.confidence_scores)

                scores = result.confidence_scores
                row = {
                    "positive": scores.positive,
                    "neutral": scores.neutral,
                    "negative": scores.negative,
                }
                broker_profiles[sender]["sentiments"].append(row)

                # Now do NER on the same text
                ner_response = client.recognize_entities(documents=[body_text])
                ner_result = ner_response[0]
                if not ner_result.is_error:
                    entities = getattr(ner_result, "entities", None)
                    if entities:
                        broker_meta = summarize_broker_entities(entities)
                        # Add to broker profile
                        for org in broker_meta["organizations"]:
                            broker_profiles[sender]["companies"].add(org)
                        for person in broker_meta["people"]:
                            broker_profiles[sender]["contacts"].add(person)
                        for email in broker_meta["emails"]:
                            broker_profiles[sender]["contact_emails"].add(email)
                        
                        print("\nNER Results (Broker entities):")
                        print("Names:", ", ".join(broker_meta["people"]) or "None")
                        print("Company:", ", ".join(broker_meta["organizations"]) or "None")
                        print("Email:", ", ".join(broker_meta["emails"]) or "None")
        else:
            print("Sentiment analysis skipped (missing LANGUAGE_ENDPOINT).")

    # Generate broker profiles
    if broker_profiles:
        print("\n" + "=" * 70)
        print("BROKER PROFILES")
        print("=" * 70)
        for sender, profile in broker_profiles.items():
            if profile["sentiments"]:
                avg_positive = sum(s["positive"] for s in profile["sentiments"]) / len(profile["sentiments"])
                avg_neutral = sum(s["neutral"] for s in profile["sentiments"]) / len(profile["sentiments"])
                avg_negative = sum(s["negative"] for s in profile["sentiments"]) / len(profile["sentiments"])
            else:
                avg_positive = avg_neutral = avg_negative = 0

            print(f"\nBroker Email: {sender}")
            print(f"  Messages: {len(profile['emails'])}")
            print(f"  Overall Sentiment:")
            print(f"    Positive: {avg_positive:.2f}")
            print(f"    Neutral: {avg_neutral:.2f}")
            print(f"    Negative: {avg_negative:.2f}")
            print(f"  Companies: {', '.join(sorted(profile['companies'])) or 'Unknown'}")
            print(f"  Contacts: {', '.join(sorted(profile['contacts'])) or 'Unknown'}")
            print(f"  Contact Emails: {', '.join(sorted(profile['contact_emails'])) or 'Unknown'}")
            print(f"  Email Subjects: {', '.join(profile['emails'])}")


def main() -> None:
    cfg = get_config()
    if not cfg.get("CLIENT_ID"):
        print("Missing required configuration. Provide via environment variables or a local secrets.json.")
        print("Required: CLIENT_ID")
        sys.exit(1)

    token = acquire_interactive_token(cfg["CLIENT_ID"])
    if not token:
        sys.exit(1)

    list_inbox_messages(token, cfg.get("LANGUAGE_ENDPOINT"))


if __name__ == "__main__":
    main()
