# Azure OpenAI Configuration for Hybrid Briefing

## Required secrets.json Configuration

You **absolutely need** Azure OpenAI credentials. Here's the complete setup:

### Complete secrets.json Template

```json
{
  "LANGUAGE_ENDPOINT": "https://[region].cognitiveservices.azure.com/",
  "LANGUAGE_KEY": "your-azure-language-key",
  
  "OPENAI_API_KEY": "your-azure-openai-api-key",
  "OPENAI_ENDPOINT": "https://[name].openai.azure.com/",
  "OPENAI_MODEL": "gpt-3.5-turbo",
  
  "COSMOS_CONNECTION_STRING": "AccountEndpoint=https://[name].documents.azure.com:443/;AccountKey=..."
}
```

### What Each Key Does

| Key | Purpose | Example | Required? |
|-----|---------|---------|-----------|
| `LANGUAGE_ENDPOINT` | Azure Language Service endpoint | `https://eastus.cognitiveservices.azure.com/` | ✅ YES (extraction) |
| `LANGUAGE_KEY` | Azure Language Service API key | (32 char string) | ✅ YES (extraction) |
| `OPENAI_API_KEY` | Azure OpenAI API key | (varies by region) | ✅ YES (LLM wrapper) |
| `OPENAI_ENDPOINT` | Azure OpenAI resource URL | `https://myresource.openai.azure.com/` | ✅ YES (LLM wrapper) |
| `OPENAI_MODEL` | Model deployment name | `gpt-3.5-turbo` or `gpt-4` | ✅ YES (LLM wrapper) |
| `COSMOS_CONNECTION_STRING` | Cosmos DB connection | (full connection string) | ⚠️ Optional (storage) |

---

## How to Get Azure OpenAI Credentials

### Step 1: Create Azure OpenAI Resource

```bash
# Via Azure CLI
az cognitiveservices account create \
  --name my-openai-resource \
  --resource-group my-resource-group \
  --kind OpenAI \
  --sku s0 \
  --location eastus
```

Or via Azure Portal: Create resource → "Azure OpenAI"

### Step 2: Deploy a Model

```bash
# Deploy gpt-3.5-turbo
az cognitiveservices account deployment create \
  --resource-group my-resource-group \
  --name my-openai-resource \
  --deployment-name gpt-3.5-turbo \
  --model-name gpt-3.5-turbo \
  --model-version "0613"
```

Or via Portal: Go to resource → "Model deployments" → "Create new deployment"

### Step 3: Get Credentials

```bash
# Get API key
az cognitiveservices account keys list \
  --name my-openai-resource \
  --resource-group my-resource-group

# Get endpoint
az cognitiveservices account show \
  --name my-openai-resource \
  --resource-group my-resource-group \
  --query "properties.endpoint"
```

Or via Portal: Settings → "Keys and Endpoint"

---

## What LLM Is Being Used?

### In underwriter_briefing.py

**Default Model: `gpt-3.5-turbo`**

The `generate_narrative_wrapper()` method accepts a `model` parameter:

```python
def generate_narrative_wrapper(
    self, 
    briefing: UnderwriterBriefing, 
    openai_client,
    model: str = "gpt-3.5-turbo"  # ← DEFAULT
) -> str:
```

### How to Change the Model

**Option 1: Use default (fastest, cheapest)**
```python
narrative = generator.generate_narrative_wrapper(briefing, openai_client)
# Uses gpt-3.5-turbo
```

**Option 2: Specify a different model**
```python
narrative = generator.generate_narrative_wrapper(
    briefing, 
    openai_client,
    model="gpt-4"  # ← More powerful, slower, more expensive
)
```

**Option 3: Use config from secrets.json**
```python
cfg = get_config()
narrative = generator.generate_narrative_wrapper(
    briefing, 
    openai_client,
    model=cfg.get("OPENAI_MODEL", "gpt-3.5-turbo")
)
```

---

## Complete Example: Proper Azure OpenAI Setup

Here's how to properly initialize the client and use the wrapper:

```python
from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI
import json
import underwriter_briefing as ub

# Load configuration
def load_config():
    with open("secrets.json", "r") as f:
        return json.load(f)

cfg = load_config()

# ============ Initialize Azure Language Client (for extraction) ============
language_client = TextAnalyticsClient(
    endpoint=cfg["LANGUAGE_ENDPOINT"],
    credential=AzureKeyCredential(cfg["LANGUAGE_KEY"])
)

# ============ Initialize Azure OpenAI Client (for LLM wrapper) ============
openai_client = AzureOpenAI(
    api_key=cfg["OPENAI_API_KEY"],
    api_version="2024-02-15-preview",  # Important: use correct API version
    azure_endpoint=cfg["OPENAI_ENDPOINT"]
)

# ============ Extract briefing ============
generator = ub.BriefingGenerator(language_client)
briefing = generator.generate_briefing(
    broker_email="shreyas@acme.com",
    body_text=email_body,
    subject="Policy Renewal",
    sender_name="Shreyas",
    sender_company="Acme Manufacturing"
)

print("✅ Extraction complete")

# ============ Generate LLM narrative ============
narrative = generator.generate_narrative_wrapper(
    briefing,
    openai_client,
    model=cfg.get("OPENAI_MODEL", "gpt-3.5-turbo")
)

print(f"✅ Narrative generated using {cfg.get('OPENAI_MODEL')}")
print(f"\nNarrative:\n{narrative}")

# ============ View combined output ============
output = briefing.to_dict()
print(f"\n✅ Briefing includes:")
print(f"  - Sentiment: {output['sections']['2_sentiment_and_tone']['overall_sentiment']}")
print(f"  - Narrative: {output['metadata']['narrative_summary'][:100]}...")
print(f"  - Model used: {output['metadata']['narrative_model']}")
```

---

## API Version Note

⚠️ **Important:** Use the correct API version for `AzureOpenAI`:

```python
# For 2024-02-15-preview (recommended)
openai_client = AzureOpenAI(
    api_key=cfg["OPENAI_API_KEY"],
    api_version="2024-02-15-preview",
    azure_endpoint=cfg["OPENAI_ENDPOINT"]
)

# Or for older versions:
# api_version="2023-12-01-preview"
# api_version="2023-05-15"
```

Check [Azure OpenAI API versions](https://learn.microsoft.com/en-us/azure/ai-services/openai/reference) for the latest.

---

## Cost Comparison: Models Available

| Model | Speed | Cost/Token | Use Case |
|-------|-------|-----------|----------|
| gpt-3.5-turbo | Fast | $0.0005/prompt, $0.0015/completion | Recommended (default) |
| gpt-4 | Slower | $0.03/prompt, $0.06/completion | Better reasoning, quality |
| gpt-4-turbo | Medium | $0.01/prompt, $0.03/completion | Faster gpt-4 |

**Recommendation:** Start with `gpt-3.5-turbo`. It's 6-10x cheaper and works well for grounded narratives.

---

## Troubleshooting

### Error: "Invalid deployment name"
```
❌ openai.error.AuthenticationError: Invalid deployment name
```
**Fix:** Ensure `OPENAI_MODEL` matches your actual deployment name in Azure Portal

```python
# Check what you deployed
# Go to: Azure Portal → Resource → Model deployments
# Example deployment names:
# - "gpt-3.5-turbo"
# - "gpt-35-turbo"  ← Different!
# - "gpt-4"
```

### Error: "Invalid API version"
```
❌ openai.error.AuthenticationError: Unsupported API version
```
**Fix:** Update API version in `AzureOpenAI` initialization

```python
# Try this version (most compatible)
openai_client = AzureOpenAI(
    api_key=cfg["OPENAI_API_KEY"],
    api_version="2024-02-15-preview",  # ← Explicitly set
    azure_endpoint=cfg["OPENAI_ENDPOINT"]
)
```

### Error: "Connection failed"
```
❌ requests.exceptions.ConnectionError
```
**Fix:** Verify endpoint format

```python
# ❌ WRONG
"https://myresource.cognitiveservices.azure.com/"

# ✅ CORRECT
"https://myresource.openai.azure.com/"
```

---

## Summary

### What You Need in secrets.json

```json
{
  "LANGUAGE_ENDPOINT": "https://[region].cognitiveservices.azure.com/",
  "LANGUAGE_KEY": "[32-char key]",
  "OPENAI_API_KEY": "[api key]",
  "OPENAI_ENDPOINT": "https://[name].openai.azure.com/",
  "OPENAI_MODEL": "gpt-3.5-turbo"
}
```

### What LLM Is Used

- **Default:** `gpt-3.5-turbo` (fast, cheap, works great)
- **Customizable:** Pass `model="gpt-4"` to use better model
- **From config:** Use `cfg.get("OPENAI_MODEL")` to make it configurable

### How to Initialize

```python
openai_client = AzureOpenAI(
    api_key=cfg["OPENAI_API_KEY"],
    api_version="2024-02-15-preview",
    azure_endpoint=cfg["OPENAI_ENDPOINT"]
)

narrative = generator.generate_narrative_wrapper(
    briefing,
    openai_client,
    model=cfg.get("OPENAI_MODEL", "gpt-3.5-turbo")
)
```

All set! You're now ready to use the hybrid briefing with proper Azure OpenAI credentials. 🚀
