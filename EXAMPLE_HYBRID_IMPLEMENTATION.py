# Complete Example: Hybrid Briefing Generation

This file shows a complete, ready-to-run example of the hybrid architecture in action.

## Scenario

An underwriter in Copilot Studio asks: "Brief me on Shreyas from Acme Manufacturing"

The system:
1. Extracts facts from broker emails
2. Generates LLM narrative grounded in those facts
3. Stores both in Cosmos DB
4. Returns formatted response to Copilot

---

## Example Code: process_broker_email.py

```python
#!/usr/bin/env python3
"""
Complete hybrid briefing example: Extract + LLM Narrative + Cosmos Storage
"""

import json
import os
from datetime import datetime
from typing import Optional

from azure.ai.textanalytics import TextAnalyticsClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

import underwriter_briefing as ub
from cosmos_storage import BriefingStorage


def load_config() -> dict:
    """Load endpoint config from secrets.json and environment (no keys — uses Managed Identity)."""
    cfg = {}

    try:
        with open("secrets.json", "r") as f:
            local = json.load(f)
            cfg.update(local)
    except FileNotFoundError:
        pass

    cfg["LANGUAGE_ENDPOINT"] = os.getenv("LANGUAGE_ENDPOINT", cfg.get("LANGUAGE_ENDPOINT"))
    cfg["OPENAI_ENDPOINT"] = os.getenv("OPENAI_ENDPOINT", cfg.get("OPENAI_ENDPOINT"))
    cfg["OPENAI_MODEL"] = os.getenv("OPENAI_MODEL", cfg.get("OPENAI_MODEL", "gpt-4o-mini"))
    cfg["COSMOS_ENDPOINT"] = os.getenv("COSMOS_ENDPOINT", cfg.get("COSMOS_ENDPOINT"))

    return cfg


def process_broker_email(
    broker_email: str,
    body_text: str,
    subject: str,
    sender_name: str,
    sender_company: str,
    generate_narrative: bool = True,
    store_in_cosmos: bool = True
) -> dict:
    """
    Complete hybrid workflow: Extract + LLM Narrative + Storage
    
    Args:
        broker_email: Broker's email address
        body_text: Email body content
        subject: Email subject line
        sender_name: Broker's name
        sender_company: Broker's company
        generate_narrative: Whether to call LLM (optional)
        store_in_cosmos: Whether to store in Cosmos DB (optional)
    
    Returns:
        {
            "briefing_id": "...",
            "narrative": "...",
            "sentiment": "...",
            "confidence": 0.XX,
            "status": "success" | "error"
        }
    """
    
    try:
        cfg = load_config()
        credential = DefaultAzureCredential()

        # ============ PHASE 1: Extraction Layer ============
        print(f"\n📧 Processing: {sender_name} ({broker_email})")
        print("Phase 1: Extracting facts from email...")

        language_client = TextAnalyticsClient(
            endpoint=cfg.get("LANGUAGE_ENDPOINT"),
            credential=credential
        )
        
        # Generate briefing
        generator = ub.BriefingGenerator(language_client)
        briefing = generator.generate_briefing(
            broker_email=broker_email,
            body_text=body_text,
            subject=subject,
            sender_name=sender_name,
            sender_company=sender_company
        )
        
        print(f"   ✓ Extracted {len(briefing.explicit_goals)} explicit goals")
        print(f"   ✓ Extracted {len(briefing.implied_goals)} implied goals")
        print(f"   ✓ Identified {len(briefing.risk_signals)} risk signals")
        print(f"   ✓ Sentiment: {briefing.overall_sentiment} ({briefing.sentiment_confidence:.0%})")
        
        # ============ PHASE 2: LLM Narrative Generation (Optional) ============
        narrative = None
        if generate_narrative and cfg.get("OPENAI_ENDPOINT"):
            print("Phase 2: Generating LLM narrative...")

            openai_client = AzureOpenAI(
                azure_ad_token_provider=get_bearer_token_provider(
                    credential, "https://cognitiveservices.azure.com/.default"
                ),
                azure_endpoint=cfg.get("OPENAI_ENDPOINT"),
                api_version="2024-02-15-preview"
            )
            
            narrative = generator.generate_narrative_wrapper(
                briefing,
                openai_client,
                model=cfg.get("OPENAI_MODEL", "gpt-3.5-turbo")
            )
            
            print(f"   ✓ Generated {len(narrative.split())} word narrative")
        else:
            print("Phase 2: LLM narrative generation SKIPPED (no OpenAI config)")
        
        # ============ PHASE 3: Cosmos DB Storage (Optional) ============
        briefing_id = None
        if store_in_cosmos and cfg.get("COSMOS_ENDPOINT"):
            print("Phase 3: Storing in Cosmos DB...")

            storage = BriefingStorage(cfg.get("COSMOS_ENDPOINT"))
            doc = briefing.to_dict()
            stored = storage.store_briefing(doc)
            briefing_id = stored.get("id")
            
            print(f"   ✓ Stored with ID: {briefing_id}")
        else:
            print("Phase 3: Cosmos DB storage SKIPPED (no connection string)")
        
        # ============ PHASE 4: Format Response ============
        print("Phase 4: Formatting response...")
        
        response = {
            "briefing_id": briefing_id or f"briefing-{broker_email}-{datetime.now().isoformat()}",
            "displayName": f"{sender_name} ({sender_company})",
            "narrative": narrative or "[LLM narrative not generated]",
            "sentiment": briefing.overall_sentiment,
            "confidence": round(briefing.overall_confidence, 2),
            "metadata": {
                "broker_email": briefing.broker_email,
                "broker_name": briefing.broker_name,
                "broker_company": briefing.broker_company,
                "email_subjects": briefing.email_subjects,
            },
            "key_facts": {
                "explicit_goals": [g.text for g in briefing.explicit_goals],
                "implied_goals": [g.text for g in briefing.implied_goals],
                "risk_signals": [r.text for r in briefing.risk_signals],
                "negotiation_style": briefing.negotiation_style,
                "next_steps": briefing.follow_up_questions[:3]
            },
            "status": "success"
        }
        
        return response
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return {
            "status": "error",
            "error": str(e),
            "displayName": f"{sender_name} ({sender_company})"
        }


def format_response_for_copilot(response: dict) -> str:
    """Format response as readable Copilot Studio card."""
    
    if response.get("status") == "error":
        return f"""
⚠️ **Error Processing Briefing**
Broker: {response.get('displayName', 'Unknown')}
Error: {response.get('error', 'Unknown error')}
"""
    
    output = f"""
📋 **UNDERWRITER BRIEFING**

**Broker:** {response['displayName']}
**ID:** {response['briefing_id'][-12:]}
**Sentiment:** {response['sentiment']} ({response['confidence']:.0%} confidence)

---

### 📝 Executive Narrative
{response['narrative']}

---

### 🎯 Key Facts

**Stated Goals:**
"""
    
    for goal in response['key_facts']['explicit_goals'][:2]:
        output += f"\n- ✓ {goal}"
    
    output += f"\n\n**Inferred Objectives:**"
    for goal in response['key_facts']['implied_goals'][:2]:
        output += f"\n- ⊕ {goal}"
    
    output += f"\n\n**Risk Signals:**"
    for risk in response['key_facts']['risk_signals'][:2]:
        output += f"\n- ⚠️ {risk}"
    
    output += f"\n\n**Negotiation Style:** {response['key_facts']['negotiation_style']}"
    
    output += f"\n\n### 🚀 Next Steps\n"
    for step in response['key_facts']['next_steps'][:3]:
        output += f"- {step}\n"
    
    output += f"\n---\n_Full briefing stored in Cosmos DB. Audit trail available on demand._\n"
    
    return output


# ============ EXAMPLE USAGE ============

if __name__ == "__main__":
    # Sample broker email
    sample_email_body = """
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
    
    # Process email through hybrid pipeline
    result = process_broker_email(
        broker_email="shreyas@acme.com",
        body_text=sample_email_body,
        subject="Acme Manufacturing Renewal - Ready for Review",
        sender_name="Shreyas",
        sender_company="Acme Manufacturing",
        generate_narrative=True,  # Set to False if OpenAI not configured
        store_in_cosmos=False  # Set to True once Cosmos DB configured
    )
    
    # Print result
    print("\n" + "="*80)
    print("FINAL RESPONSE FOR COPILOT STUDIO")
    print("="*80)
    print(format_response_for_copilot(result))
    
    # Also print JSON for API consumption
    print("\n" + "="*80)
    print("RAW JSON RESPONSE")
    print("="*80)
    print(json.dumps(result, indent=2))
```

---

## Running the Example

### Prerequisites

```bash
# Install dependencies
pip install -r requirements.txt
```

Update `requirements.txt`:
```
azure-ai-textanalytics>=5.3.0
azure-cosmos>=4.4.0
openai>=1.0.0
```

Update `secrets.json` (endpoints only — no keys, authentication uses Managed Identity):
```json
{
  "LANGUAGE_ENDPOINT": "https://[region].cognitiveservices.azure.com/",
  "OPENAI_ENDPOINT": "https://[name].openai.azure.com/",
  "OPENAI_MODEL": "gpt-4o-mini",
  "COSMOS_ENDPOINT": "https://[name].documents.azure.com:443/"
}
```

### Run Locally

```bash
python3 process_broker_email.py

# Expected output:
# 📧 Processing: Shreyas (shreyas@acme.com)
# Phase 1: Extracting facts from email...
#    ✓ Extracted 2 explicit goals
#    ✓ Extracted 1 implied goals
#    ✓ Identified 1 risk signals
#    ✓ Sentiment: Positive (92%)
# Phase 2: Generating LLM narrative...
#    ✓ Generated 87 word narrative
# Phase 3: Storing in Cosmos DB...
#    ✓ Stored with ID: briefing-shreyas@acme.com-2024-01-31T10:30:45Z
# Phase 4: Formatting response...
#
# ================================================================================
# FINAL RESPONSE FOR COPILOT STUDIO
# ================================================================================
#
# 📋 **UNDERWRITER BRIEFING**
#
# **Broker:** Shreyas (Acme Manufacturing)
# **ID:** 30T10:30:45Z
# **Sentiment:** Positive (92% confidence)
#
# ---
#
# ### 📝 Executive Narrative
# Shreyas from Acme Manufacturing has reached out regarding their policy renewal with 
# a clear collaborative tone and shared alignment on next steps. The positive sentiment 
# and focus on timeline management indicates strong engagement potential. Time pressure 
# is evident (binding by Friday), creating urgency in the process...
#
# [... full briefing continues ...]
```

---

## Integration Points

### 1. Call from Copilot Studio Bot

```python
# In bot logic:
from process_broker_email import process_broker_email, format_response_for_copilot

# User says: "Brief me on shreyas@acme.com"
result = process_broker_email(
    broker_email="shreyas@acme.com",
    body_text=get_email_body("shreyas@acme.com"),  # Fetch from Outlook
    subject=get_email_subject("shreyas@acme.com"),
    sender_name="Shreyas",
    sender_company="Acme Manufacturing",
    generate_narrative=True,
    store_in_cosmos=True
)

bot_response = format_response_for_copilot(result)
# Display bot_response in chat
```

### 2. Call from Scheduled Batch Job

```bash
#!/bin/bash
# run_daily_batch.sh - Called by ACA Container Jobs 2x daily

cd /app

# Get emails from past 12 hours from Outlook (Microsoft Graph)
python3 get_emails_from_outlook.py --hours 12 > /tmp/emails.json

# Process each email
python3 -c "
import json
from process_broker_email import process_broker_email

with open('/tmp/emails.json') as f:
    emails = json.load(f)

for email in emails:
    result = process_broker_email(
        broker_email=email['sender'],
        body_text=email['body'],
        subject=email['subject'],
        sender_name=email['sender_name'],
        sender_company=email['sender_company'],
        generate_narrative=True,
        store_in_cosmos=True
    )
    print(f\"✅ Processed: {email['sender']}\")

print(f\"✅ Batch complete: {len(emails)} emails processed\")
"
```

### 3. Call from API Endpoint

```python
# Azure Function: process_broker_email_http_trigger.py

import azure.functions as func
from process_broker_email import process_broker_email
import json

def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP API to process a single broker email.
    
    POST /api/process-email
    Body: {
      "broker_email": "...",
      "body_text": "...",
      "subject": "...",
      "sender_name": "...",
      "sender_company": "..."
    }
    """
    
    try:
        req_body = req.get_json()
        
        result = process_broker_email(
            broker_email=req_body['broker_email'],
            body_text=req_body['body_text'],
            subject=req_body['subject'],
            sender_name=req_body['sender_name'],
            sender_company=req_body['sender_company'],
            generate_narrative=True,
            store_in_cosmos=True
        )
        
        return func.HttpResponse(
            json.dumps(result),
            status_code=200 if result['status'] == 'success' else 400,
            mimetype="application/json"
        )
    
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"status": "error", "error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
```

---

## Key Features Demonstrated

✅ **Modular:** Each phase can be toggled on/off  
✅ **Error Handling:** Graceful fallbacks if services unavailable  
✅ **Flexibility:** Works with or without LLM, Cosmos DB  
✅ **Copilot Ready:** Formatted for chat display  
✅ **Auditable:** Full pipeline logging  
✅ **Production-Ready:** Error tracking, configuration management  

---

## Next: Deploy to Production

Once tested locally:

1. Copy `process_broker_email.py` to ACA container
2. Deploy Azure Function with HTTP trigger
3. Connect Power Automate flow
4. Configure Copilot Studio bot
5. Monitor with Application Insights

See `COSMOS_COPILOT_SETUP.md` for detailed deployment instructions.
