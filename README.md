# Underwriter Briefing Pipeline

Azure Functions pipeline that processes broker emails into structured underwriter briefings using Azure AI Language Service (NER/sentiment), Azure OpenAI (narrative generation), and Cosmos DB (storage).

---

## Architecture

```
Broker Email (via Graph API)
    ↓
Azure AI Language Service  — sentiment, NER, key phrase extraction
    ↓
10-Section Structured Briefing (JSON)
    ↓
Azure OpenAI  — grounded narrative generation
    ↓
Cosmos DB  — persistent storage
    ↓
Azure Function HTTP API
    ↓
Power Automate → Copilot Studio
```

---

## Authentication: Managed Identity instead of API Keys

This pipeline authenticates to Azure AI Language Service, Azure OpenAI, and Cosmos DB using **Managed Identity** rather than API keys. No keys are stored in config files or environment variables.

### How it works

When the Function App runs on Azure, it has a system-assigned identity in Entra ID. You grant that identity permission to call each service via RBAC role assignments. At runtime, the app exchanges its identity for a short-lived bearer token (issued by Entra ID, valid ~1 hour, auto-refreshed) and presents that token when calling each service — no key is ever involved.

### Setup (one-time, in Azure Portal)

**1. Enable Managed Identity on the Function App**

```
Function App → Identity → System assigned → On
```

This creates a service principal in Entra ID named after your Function App.

**2. Assign RBAC roles**

| Service | Role | Where to assign |
|---|---|---|
| Azure OpenAI | `Cognitive Services OpenAI User` | OpenAI resource → Access Control (IAM) |
| Language Service | `Cognitive Services User` | Language resource → Access Control (IAM) |
| Cosmos DB | `Cosmos DB Built-in Data Contributor` | Cosmos account → Access Control (IAM) |

For each: go to the resource → **Access Control (IAM)** → **Add role assignment** → select the role → assign to your Function App's service principal.

**3. Remove keys from app settings**

Delete `LANGUAGE_KEY`, `OPENAI_API_KEY`, and `COSMOS_KEY` from Function App environment variables. Only endpoints are needed:

```
LANGUAGE_ENDPOINT  = https://[region].cognitiveservices.azure.com/
OPENAI_ENDPOINT    = https://[name].openai.azure.com/
COSMOS_ENDPOINT    = https://[name].documents.azure.com:443/
OPENAI_MODEL       = gpt-4o-mini
```

### How the code uses it

```python
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.ai.textanalytics import TextAnalyticsClient
from openai import AzureOpenAI

credential = DefaultAzureCredential()

# Language Service — credential accepted directly
language_client = TextAnalyticsClient(
    endpoint=os.getenv("LANGUAGE_ENDPOINT"),
    credential=credential
)

# Azure OpenAI — requires a token provider wrapper
openai_client = AzureOpenAI(
    azure_ad_token_provider=get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default"
    ),
    api_version="2024-02-15-preview",
    azure_endpoint=os.getenv("OPENAI_ENDPOINT")
)
```

`DefaultAzureCredential` automatically picks up the Managed Identity when running on Azure, and falls back to your `az login` session for local development — same code, no changes between environments.

### Local development

Run `az login` before starting the app locally. Your personal Entra ID account needs the same RBAC roles assigned to it that the Function App's MI has in production.

`secrets.json` for local dev (endpoints only, no keys):

```json
{
  "LANGUAGE_ENDPOINT": "https://[region].cognitiveservices.azure.com/",
  "OPENAI_ENDPOINT": "https://[name].openai.azure.com/",
  "OPENAI_MODEL": "gpt-4o-mini",
  "COSMOS_ENDPOINT": "https://[name].documents.azure.com:443/"
}
```

---

## Project Structure

```
function_app.py               — Azure Function HTTP triggers (GetBriefing, ProcessEmail, etc.)
underwriter_briefing.py       — Core briefing generation logic
ai_inference_module.py        — GPT-powered inference generation
batch_job_orchestrator.py     — Scheduled batch processor (ACA Jobs)
cosmos_storage.py             — Cosmos DB storage layer
regenerate_with_ai.py         — Utility: regenerate existing briefings with AI
local_api_server.py           — Flask server for local testing
examples_outlook.py           — Graph API email fetch examples
poc_live/                     — Production NRT worker (Service Bus + Graph delta)
nrt_aks/                      — AKS-based near-real-time ingestion worker
```

---

## Setup

```bash
pip install -r requirements.txt
```

Configure `secrets.json` with endpoints (see above), then:

```bash
# Local testing
python local_api_server.py

# Or run the quickstart
python quickstart_hybrid.py
```

---

## Deploy

```bash
func azure functionapp publish <your-function-app-name>
```

See `DEPLOYMENT_GUIDE.md` for full deployment steps including infrastructure setup.
