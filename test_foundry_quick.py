#!/usr/bin/env python3
"""
Quick test - proves Foundry endpoint is being hit
"""
import json
import os
from azure.identity import ClientSecretCredential
from openai import AzureOpenAI

# Load credentials
with open('secrets.json', 'r') as f:
    secrets = json.load(f)

client_id = secrets.get("AZURE_CLIENT_ID")
client_secret = secrets.get("AZURE_CLIENT_SECRET")
tenant_id = secrets.get("AZURE_TENANT_ID")
endpoint = secrets.get("OPENAI_ENDPOINT")
model = secrets.get("OPENAI_MODEL")

print(f"🔍 Endpoint being used: {endpoint}")
print(f"🔍 Model: {model}")
print()

# Create credential
credential = ClientSecretCredential(
    client_id=client_id,
    client_secret=client_secret,
    tenant_id=tenant_id
)

# Get token
token = credential.get_token("https://ai.azure.com/.default")
print(f"✅ Got Azure AD token")

# Create OpenAI client
client = AzureOpenAI(
    azure_ad_token_provider=lambda: token.token,
    api_version="2024-08-01-preview",
    azure_endpoint=endpoint
)

print(f"✅ Created OpenAI client\n")

# Make a quick call
print("📤 Sending request to Foundry...")
try:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": "Say 'Hello from Foundry' and nothing else."}
        ],
        max_tokens=20
    )
    
    result = response.choices[0].message.content
    print(f"✅ SUCCESS - Response from Foundry:\n")
    print(f"   {result}")
    print(f"\n✅ PROOF: Hit {endpoint} with {model} model")
    
except Exception as e:
    print(f"❌ Error: {str(e)}")
