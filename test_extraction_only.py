#!/usr/bin/env python3
"""
Test underwriter_briefing.py - briefing extraction only (no LLM enhancement)
"""
import sys
sys.path.insert(0, '/home/snatesan/projects/graphapp_onedrive')

from underwriter_briefing import BriefingGenerator, format_briefing_as_markdown
from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential
import json

# Load config
def load_config():
    try:
        with open('secrets.json', 'r') as f:
            return json.load(f)
    except:
        return {}

cfg = load_config()
language_endpoint = cfg.get("LANGUAGE_ENDPOINT")
language_key = cfg.get("LANGUAGE_KEY")

if not language_endpoint or not language_key:
    print("❌ Missing Language Service credentials")
    print("Add LANGUAGE_ENDPOINT and LANGUAGE_KEY to secrets.json")
    sys.exit(1)

print(f"✅ Language Service endpoint: {language_endpoint}")

# Create Text Analytics client
client = TextAnalyticsClient(
    endpoint=language_endpoint,
    credential=AzureKeyCredential(language_key)
)

# Generate briefing
generator = BriefingGenerator(client)

sample_email = """
Hi Jordan,

Wanted to let you know we've completed our initial review of the Acme Manufacturing renewal. 
The submission was well organized, and the additional context you provided was helpful. 
We're aligned on next steps and expect to have an updated indication ready shortly. 
I'll make sure you have everything you need to keep the process moving smoothly with your client.

Thanks again for the collaboration—looking forward to closing this one together.

Best,
Shreyas
"""

print("\n🔄 Extracting briefing from email...")
briefing = generator.generate_briefing(
    broker_email="shreyas@acme.com",
    body_text=sample_email,
    subject="Acme Manufacturing Renewal - Initial Review",
    sender_name="Shreyas",
    sender_company="Acme Corp"
)

print("✅ Briefing extraction complete\n")

# Output as markdown
output = format_briefing_as_markdown(briefing)
print(output)

print("\n" + "="*80)
print("📊 JSON for storage in Cosmos DB:")
print("="*80)
import json
print(json.dumps(briefing.to_dict(), indent=2)[:1500] + "...")
