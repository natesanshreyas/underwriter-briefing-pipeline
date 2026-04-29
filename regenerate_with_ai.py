#!/usr/bin/env python3
"""
Regenerate briefings with AI-driven inferences.
Run this to update all existing briefings in Cosmos DB with real AI inferences.
"""

import json
import os
from openai import AzureOpenAI
from azure.ai.textanalytics import TextAnalyticsClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from underwriter_briefing import BriefingGenerator
from cosmos_storage import BriefingStorage, get_cosmos_config

def regenerate_briefing_with_ai(briefing_data: dict):
    """Regenerate a briefing with AI inferences from Cosmos DB."""

    config = {
        "LANGUAGE_ENDPOINT": os.getenv("LANGUAGE_ENDPOINT"),
        "OPENAI_ENDPOINT": os.getenv("OPENAI_ENDPOINT"),
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    }

    credential = DefaultAzureCredential()

    language_client = TextAnalyticsClient(
        endpoint=config["LANGUAGE_ENDPOINT"],
        credential=credential
    )

    openai_client = AzureOpenAI(
        azure_ad_token_provider=get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        ),
        api_version="2024-02-15-preview",
        azure_endpoint=config["OPENAI_ENDPOINT"]
    )
    
    # Extract original data
    metadata = briefing_data.get("metadata", {})
    broker_email = metadata.get("broker_email", "unknown@unknown.com")
    broker_name = metadata.get("broker_name", "Unknown")
    broker_company = metadata.get("broker_company", "Unknown")
    email_subjects = metadata.get("email_subjects", [""])
    
    # Reconstruct email (we don't have the original body, but we can use what we have)
    # For now, we'll regenerate using metadata and existing facts
    
    # Create generator
    generator = BriefingGenerator(language_client)
    
    # Reconstruct a synthetic email from the extracted facts for re-analysis
    sections = briefing_data.get("sections", {})
    
    # Build synthetic body from facts
    synthetic_body = f"""
Subject: {email_subjects[0] if email_subjects else "Communication"}

Key facts extracted:
- Sentiment: {sections.get('2_sentiment_and_tone', {}).get('overall_sentiment', 'Unknown')}
- Stakeholders: {', '.join([s.get('name', '') for s in sections.get('3_key_relationships', {}).get('stakeholders', [])])}
- Goals: {', '.join([g.get('text', '') for g in sections.get('4_broker_priorities', {}).get('explicit_goals', [])])}
"""
    
    # Regenerate WITH AI inferences
    briefing = generator.generate_briefing(
        broker_email=broker_email,
        body_text=synthetic_body,
        subject=email_subjects[0] if email_subjects else "Renewal",
        sender_name=broker_name,
        sender_company=broker_company,
        openai_client=openai_client,  # ← WITH AI!
        openai_model=config["OPENAI_MODEL"]
    )
    
    return briefing.to_dict()


def main():
    print("🔄 Regenerating briefings with AI inferences...\n")
    
    # Load secrets
    try:
        with open("secrets.json", "r") as f:
            secrets = json.load(f)
            for key, value in secrets.items():
                os.environ[key] = str(value)
    except FileNotFoundError:
        print("❌ secrets.json not found")
        return
    
    # Connect to Cosmos DB
    cosmos_cfg = get_cosmos_config()
    storage = BriefingStorage(
        endpoint=cosmos_cfg["endpoint"],
        key=cosmos_cfg["key"],
        database_name=cosmos_cfg["database"],
        container_name=cosmos_cfg["container"]
    )
    
    # Query all briefings
    print("📂 Fetching existing briefings...\n")
    query = "SELECT * FROM c"
    briefings = list(storage.container.query_items(query=query, enable_cross_partition_query=True))
    
    if not briefings:
        print("❌ No briefings found in Cosmos DB")
        return
    
    print(f"✅ Found {len(briefings)} briefings\n")
    
    # Regenerate each
    for i, briefing_data in enumerate(briefings, 1):
        print(f"[{i}/{len(briefings)}] Regenerating: {briefing_data.get('metadata', {}).get('broker_company', 'Unknown')}")
        
        try:
            # Regenerate with AI
            new_briefing = regenerate_briefing_with_ai(briefing_data)
            
            # Update in Cosmos DB (preserve ID and partition key)
            new_briefing["id"] = briefing_data["id"]
            new_briefing["metadata"]["broker_company"] = briefing_data["metadata"]["broker_company"]
            
            # Store
            result = storage.container.upsert_item(new_briefing)
            print(f"   ✅ Updated with AI inferences")
            
            # Show what changed
            old_implied = len(briefing_data.get("sections", {}).get("4_broker_priorities", {}).get("implied_goals", []))
            new_implied = len(new_briefing.get("sections", {}).get("4_broker_priorities", {}).get("implied_goals", []))
            print(f"      Implied Goals: {old_implied} → {new_implied}")
            
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        print()
    
    print("\n✅ Regeneration complete!")


if __name__ == "__main__":
    main()
