#!/usr/bin/env python3
"""
Quick Start: Run the hybrid briefing system locally

This is the simplest way to see extraction + LLM narrative + storage in action.

Requirements:
- Python 3.11+
- Credentials in secrets.json (LANGUAGE_*, OPENAI_*, COSMOS_*)

Run:
  python3 quickstart_hybrid.py
"""

import json
import os
from datetime import datetime
from typing import Optional

# These would normally be installed via: pip install azure-ai-textanalytics azure-cosmos openai
# For testing without these, we'll make imports optional
try:
    from azure.ai.textanalytics import TextAnalyticsClient
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    HAS_AZURE = True
except ImportError:
    HAS_AZURE = False
    print("⚠️  Note: azure-ai-textanalytics not installed. Install via: pip install azure-ai-textanalytics azure-identity")

try:
    from openai import AzureOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    print("⚠️  Note: openai not installed. Install via: pip install openai")

try:
    from azure.cosmos import CosmosClient
    HAS_COSMOS = True
except ImportError:
    HAS_COSMOS = False
    print("⚠️  Note: azure-cosmos not installed. Install via: pip install azure-cosmos")

import underwriter_briefing as ub


def load_secrets() -> dict:
    """Load endpoint config from environment or secrets.json (no keys needed)."""
    cfg = {
        "LANGUAGE_ENDPOINT": os.getenv("LANGUAGE_ENDPOINT"),
        "OPENAI_ENDPOINT": os.getenv("OPENAI_ENDPOINT"),
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "COSMOS_ENDPOINT": os.getenv("COSMOS_ENDPOINT"),
    }
    if not cfg["LANGUAGE_ENDPOINT"]:
        try:
            with open("secrets.json", "r") as f:
                secrets = json.load(f)
                cfg["LANGUAGE_ENDPOINT"] = cfg["LANGUAGE_ENDPOINT"] or secrets.get("LANGUAGE_ENDPOINT")
                cfg["OPENAI_ENDPOINT"] = cfg["OPENAI_ENDPOINT"] or secrets.get("OPENAI_ENDPOINT")
                cfg["OPENAI_MODEL"] = cfg["OPENAI_MODEL"] or secrets.get("OPENAI_MODEL", "gpt-4o-mini")
                cfg["COSMOS_ENDPOINT"] = cfg["COSMOS_ENDPOINT"] or secrets.get("COSMOS_ENDPOINT")
        except FileNotFoundError:
            print("❌ ERROR: secrets.json not found!")
            print("\nCreate secrets.json with (no keys — uses Managed Identity):")
            print("""{
  "LANGUAGE_ENDPOINT": "https://[region].cognitiveservices.azure.com/",
  "OPENAI_ENDPOINT": "https://[name].openai.azure.com/",
  "OPENAI_MODEL": "gpt-4o-mini",
  "COSMOS_ENDPOINT": "https://[name].documents.azure.com:443/"
}""")
    return cfg


def run_hybrid_briefing():
    """Run complete hybrid workflow"""
    
    cfg = load_secrets()
    
    if not cfg:
        print("\n❌ Cannot proceed without credentials in secrets.json")
        return
    
    # Sample email
    sample_email = """
    Hi Jordan,
    
    Wanted to let you know we've completed our initial review of the Acme Manufacturing renewal. 
    The submission was well organized, and the additional context you provided was helpful. 
    We're aligned on next steps and expect to have an updated indication ready shortly. 
    I'll make sure you have everything you need to keep the process moving smoothly with your client.
    
    One thing worth noting: there's some competitive pressure on this one, so timing is important. 
    We'd like to get binding authority confirmed by Friday if possible.
    
    Thanks again for the collaboration—looking forward to closing this one together.
    
    Best,
    Shreyas
    """
    
    print("\n" + "="*80)
    print("HYBRID BRIEFING SYSTEM - QUICKSTART")
    print("="*80)
    
    # ============ PHASE 1: EXTRACTION ============
    print("\n📧 INPUT EMAIL:")
    print(f"From: Shreyas (shreyas@acme.com)")
    print(f"Company: Acme Manufacturing")
    print(f"Subject: Acme Manufacturing Renewal - Ready for Review")
    print(f"Body: {len(sample_email)} characters")
    
    print("\n" + "="*80)
    print("PHASE 1: EXTRACTION (Azure Language Service)")
    print("="*80)
    
    if not HAS_AZURE:
        print("⚠️  Skipping extraction (azure-ai-textanalytics not installed)")
        briefing = None
    else:
        try:
            client = TextAnalyticsClient(
                endpoint=cfg.get("LANGUAGE_ENDPOINT"),
                credential=DefaultAzureCredential()
            )
            
            generator = ub.BriefingGenerator(client)
            briefing = generator.generate_briefing(
                broker_email="shreyas@acme.com",
                body_text=sample_email,
                subject="Acme Manufacturing Renewal - Ready for Review",
                sender_name="Shreyas",
                sender_company="Acme Manufacturing"
            )
            
            print(f"\n✅ Extraction Complete!")
            print(f"\n📊 Results:")
            print(f"  • Sentiment: {briefing.overall_sentiment} ({briefing.sentiment_confidence:.0%})")
            print(f"  • Explicit Goals: {len(briefing.explicit_goals)}")
            print(f"  • Implied Goals: {len(briefing.implied_goals)}")
            print(f"  • Risk Signals: {len(briefing.risk_signals)}")
            print(f"  • Stakeholders: {len(briefing.stakeholders)}")
            print(f"  • Confidence: {briefing.overall_confidence:.0%}")
            
            print(f"\n📌 Key Facts Extracted:")
            for goal in briefing.explicit_goals[:2]:
                print(f"  • {goal.text} ({goal.confidence:.0%})")
            
        except Exception as e:
            print(f"❌ Extraction failed: {str(e)}")
            briefing = None
    
    if not briefing:
        print("\n❌ Cannot proceed without briefing. Check Azure credentials.")
        return
    
    # ============ PHASE 2: LLM NARRATIVE ============
    print("\n" + "="*80)
    print("PHASE 2: LLM NARRATIVE (OpenAI)")
    print("="*80)
    
    narrative = None
    if not HAS_OPENAI:
        print("⚠️  Skipping narrative (openai not installed)")
    elif not cfg.get("OPENAI_ENDPOINT"):
        print("⚠️  Skipping narrative (OPENAI_ENDPOINT not configured)")
    else:
        try:
            _credential = DefaultAzureCredential()
            openai_client = AzureOpenAI(
                azure_ad_token_provider=get_bearer_token_provider(
                    _credential, "https://cognitiveservices.azure.com/.default"
                ),
                azure_endpoint=cfg.get("OPENAI_ENDPOINT"),
                api_version="2024-02-15-preview"
            )
            
            narrative = generator.generate_narrative_wrapper(
                briefing,
                openai_client,
                model=cfg.get("OPENAI_MODEL", "gpt-3.5-turbo")
            )
            
            print(f"\n✅ Narrative Generated!")
            print(f"\n📝 Output ({len(narrative.split())} words):")
            print(f"\n{narrative}")
            
        except Exception as e:
            print(f"❌ Narrative generation failed: {str(e)}")
            narrative = "[LLM narrative generation unavailable]"
    
    # ============ PHASE 3: COSMOS STORAGE ============
    print("\n" + "="*80)
    print("PHASE 3: COSMOS DB STORAGE")
    print("="*80)
    
    cosmos_id = None
    if not HAS_COSMOS:
        print("⚠️  Skipping storage (azure-cosmos not installed)")
    elif not cfg.get("COSMOS_CONNECTION_STRING"):
        print("⚠️  Skipping storage (COSMOS_CONNECTION_STRING not in secrets.json)")
    else:
        try:
            from cosmos_helper import BriefingStorage
            
            storage = BriefingStorage(cfg.get("COSMOS_CONNECTION_STRING"))
            doc = briefing.to_dict()
            stored = storage.store_briefing(doc)
            cosmos_id = stored.get("id")
            
            print(f"\n✅ Document Stored!")
            print(f"\n🔗 Document ID: {cosmos_id}")
            print(f"  Partition Key: {briefing.broker_company}")
            
        except Exception as e:
            print(f"❌ Storage failed: {str(e)}")
            cosmos_id = f"local-{datetime.now().isoformat()}"
    
    # ============ PHASE 4: OUTPUT ============
    print("\n" + "="*80)
    print("PHASE 4: OUTPUT FORMATS")
    print("="*80)
    
    # Format 1: Markdown (for Copilot Studio)
    print("\n📋 MARKDOWN FORMAT (for chat display):")
    print("\n" + "-"*80)
    markdown = ub.format_briefing_as_markdown(briefing)
    print(markdown[:500] + "\n... [truncated for display] ...\n")
    
    # Format 2: Traditional report
    print("\n📄 TRADITIONAL REPORT FORMAT:")
    print("\n" + "-"*80)
    report = ub.format_briefing_for_display(briefing)
    print(report[:500] + "\n... [truncated for display] ...\n")
    
    # Format 3: JSON (for API)
    print("\n🔌 JSON FORMAT (for API/storage):")
    print("\n" + "-"*80)
    json_output = json.dumps(briefing.to_dict(), indent=2)
    print(json_output[:500] + "\n... [truncated for display] ...\n")
    
    # ============ SUMMARY ============
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    summary = {
        "status": "success",
        "phases_completed": {
            "extraction": "✅ Complete" if briefing else "❌ Failed",
            "llm_narrative": f"✅ {len(narrative.split())} words" if narrative and narrative != "[LLM narrative generation unavailable]" else "⚠️ Unavailable",
            "cosmos_storage": f"✅ {cosmos_id}" if cosmos_id else "⚠️ Not stored",
        },
        "briefing_stats": {
            "sentiment": briefing.overall_sentiment,
            "confidence": round(briefing.overall_confidence, 2),
            "explicit_goals": len(briefing.explicit_goals),
            "risk_signals": len(briefing.risk_signals),
            "stakeholders": len(briefing.stakeholders),
        },
        "narrative_length": len(narrative.split()) if narrative else 0,
        "cosmos_document_id": cosmos_id,
        "timestamp": datetime.now().isoformat(),
    }
    
    print("\n✅ HYBRID WORKFLOW COMPLETE!\n")
    print(json.dumps(summary, indent=2))
    
    # ============ NEXT STEPS ============
    print("\n" + "="*80)
    print("NEXT STEPS")
    print("="*80)
    
    next_steps = """
1. ✅ Extraction: Structured facts extracted from email with confidence scores
2. ✅ LLM Narrative: Professional summary grounded in extracted facts
3. ✅ Storage: Document stored in Cosmos DB with full audit trail

To integrate with Copilot Studio:

1. Create Azure Function HTTP trigger:
   - Method: GET /api/GetBriefing?email=shreyas@acme.com
   - Returns: Formatted response with narrative + briefing

2. Connect Power Automate flow:
   - Trigger: Email arrives in shared mailbox
   - Action: Call GetBriefing function
   - Notify Copilot Studio bot

3. Add Copilot Studio topic:
   - Trigger phrase: "Brief me on {email}"
   - Action: Display response card with narrative

4. Deploy to production:
   - Container: ACA Container Jobs
   - Schedule: 2x daily batch processing
   - Monitor: Application Insights

See IMPLEMENTATION_SUMMARY.md for details.
"""
    
    print(next_steps)


if __name__ == "__main__":
    run_hybrid_briefing()
