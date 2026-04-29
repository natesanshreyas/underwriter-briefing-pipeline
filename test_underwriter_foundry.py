#!/usr/bin/env python3
"""
Simple test of underwriter_briefing.py using Foundry with Azure AD
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
    sys.exit(1)

print(f"✓ Language Service configured: {language_endpoint}")

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

briefing = generator.generate_briefing(
    broker_email="shreyas@acme.com",
    body_text=sample_email,
    subject="Acme Manufacturing Renewal - Initial Review",
    sender_name="Shreyas",
    sender_company="Acme Corp"
)

print("✓ Briefing extraction complete")

# Try LLM enhancement with Foundry
try:
    from openai import AzureOpenAI
    from azure.identity import DefaultAzureCredential
    
    credential = DefaultAzureCredential()
    openai_client = AzureOpenAI(
        azure_ad_token_provider=lambda: credential.get_token("https://ai.azure.com/.default").token,
        api_version="2024-08-01-preview",
        azure_endpoint="https://shreyasfoundry111111.services.ai.azure.com/"
    )
    
    print("✓ OpenAI client created with Azure AD (Foundry)")
    
    briefing = generator.generate_narrative_wrapper(
        briefing,
        openai_client,
        model="DeepSeek-V3.2"
    )
    
    print("✓ LLM enhancement complete")
except Exception as e:
    print(f"⚠ LLM enhancement failed: {str(e)[:200]}")

# Output
print("\n" + "="*80)
print("MARKDOWN OUTPUT")
print("="*80)
print(format_briefing_as_markdown(briefing))
