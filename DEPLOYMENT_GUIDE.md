# Deployment Guide: Underwriter Briefing Agent + Batch Pipeline

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Deployed Cloud Infrastructure                │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │           ACA Apps (Agent Frontend)                      │    │
│  │  - FastAPI + Uvicorn running on 8080                    │    │
│  │  - Static frontend (HTML/JS)                            │    │
│  │  - Handles chat requests from users                     │    │
│  │  - Calls Azure Functions API for data                   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              ↕                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │        Azure Functions API (Already Deployed)            │    │
│  │  - underwriter-briefing-api.azurewebsites.net           │    │
│  │  - 5 endpoints: GetBriefing, SearchBriefings, etc.      │    │
│  │  - Requires function key authentication                 │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              ↕                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │         Cosmos DB (Already Deployed)                     │    │
│  │  - shreyas-underwriter-db                               │    │
│  │  - Database: UnderwriterDB                              │    │
│  │  - Container: Briefings                                 │    │
│  │  - Partition key: /metadata/broker_company              │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │      ACA Jobs (Batch Pipeline - Scheduled)               │    │
│  │  - Cron trigger: 9 AM daily (configurable)              │    │
│  │  - Fetches emails from Outlook via Graph API            │    │
│  │  - Generates briefings using Azure Language Service     │    │
│  │  - Stores in Cosmos DB                                  │    │
│  │  - Exits after completion (stateless)                   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

### 1. Azure Resources (Already Have ✅)
- ✅ Azure Functions API deployed
- ✅ Cosmos DB created and configured
- ✅ Azure Language Service
- ✅ Azure OpenAI

### 2. New Resources to Create
- [ ] Azure Container Registry (ACR) - for storing Docker images
- [ ] Azure Container Apps (ACA) - for agent app + batch jobs

### 3. Tools Required
- Azure CLI 2.50+
- Docker (running)
- ACA extension for Azure CLI

```bash
# Install/update tools
az upgrade
az extension add -n containerapp
```

---

## Step 1: Create Azure Container Registry (ACR)

```bash
# Choose a unique name (lowercase, alphanumeric only)
ACR_NAME="shreyas123"  # Change this!
RESOURCE_GROUP="your-resource-group"
LOCATION="eastus"

# Create ACR
az acr create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACR_NAME" \
  --sku Basic

# Get login credentials
az acr credential show --name "$ACR_NAME"
```

---

## Step 2: Update Deployment Configuration

Edit `deploy.sh` and set your values:

```bash
# Line 16-19 in deploy.sh:
RESOURCE_GROUP="your-resource-group"  # e.g., "my-insurance-rg"
ACR_NAME="shreyas123"                 # e.g., "shreyas123" (must be unique)
LOCATION="eastus"                     # Azure region
```

---

## Step 3: Set Environment Variables

Before deployment, export these credentials:

```bash
export OPENAI_API_KEY="your-openai-key"
export OPENAI_ENDPOINT="your-openai-endpoint"
export LANGUAGE_ENDPOINT="your-language-endpoint"
export LANGUAGE_KEY="your-language-key"
export COSMOS_ENDPOINT="your-cosmos-endpoint"
export COSMOS_KEY="your-cosmos-key"
export GRAPH_TENANT_ID="your-tenant-id"
export GRAPH_CLIENT_ID="your-client-id"
export GRAPH_CLIENT_SECRET="your-client-secret"
```

Or load from secrets.json:

```bash
source <(jq -r 'to_entries | .[] | "export \(.key)=\(.value)"' secrets.json)
```

---

## Step 4: Deploy

```bash
# Make script executable
chmod +x deploy.sh

# Run deployment
./deploy.sh
```

This will:
1. ✅ Build `Dockerfile.agent` → agent image
2. ✅ Build `Dockerfile.batch` → batch job image
3. ✅ Push both to ACR
4. ✅ Deploy agent to ACA Apps (public URL)
5. ✅ Deploy batch job to ACA Jobs (scheduled daily 9am)

---

## Step 5: Monitor Deployments

### Agent (ACA Apps)

```bash
# Get the public URL
az containerapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-agent" \
  --query "properties.configuration.ingress.fqdn"

# View logs
az containerapp logs show \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-agent" \
  --follow

# Check status
az containerapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-agent" \
  --query "properties.provisioningState"
```

### Batch Job (ACA Jobs)

```bash
# View execution history
az containerapp job execution list \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-batch"

# View latest execution logs
LATEST_EXEC=$(az containerapp job execution list \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-batch" \
  --query "[0].name" -o tsv)

az containerapp job logs show \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-batch" \
  --execution "$LATEST_EXEC"

# Trigger manual execution
az containerapp job start \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-batch"
```

---

## Step 6: Update Batch Job Schedule (Optional)

Default is **9 AM daily**. To change:

```bash
# Edit the cron expression
# Format: minute hour * * * (cron syntax)
# Examples:
#   0 9 * * *     = 9 AM daily
#   0 9 * * MON   = 9 AM Mondays only
#   0 9,17 * * *  = 9 AM and 5 PM daily

az containerapp job update \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-batch" \
  --cron-expression "0 9,17 * * *"  # 9 AM and 5 PM
```

---

## Step 7: Verify End-to-End

### Test Agent Frontend

1. Navigate to the ACA Apps URL (from step 5)
2. Should see: **"Underwriter Briefing Assistant"** interface
3. Try asking: "Show me briefings for acme@example.com"
4. Should query Cosmos DB through Azure Functions API

### Test Batch Job

1. Manually trigger: `az containerapp job start ...`
2. Check logs for execution
3. Verify new briefings appear in Cosmos DB

```bash
# Query Cosmos DB directly
az cosmosdb database show \
  --resource-group "$RESOURCE_GROUP" \
  --name "shreyas-underwriter-db"
```

---

## Troubleshooting

### Agent not accessible
```bash
# Check ingress configuration
az containerapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-agent" \
  --query "properties.configuration.ingress"

# Check container logs
az containerapp logs show \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-agent"
```

### Batch job not running
```bash
# Check schedule
az containerapp job show \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-batch" \
  --query "properties.configuration.triggerConfig"

# Check for execution errors
az containerapp job logs show \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-batch"
```

### Container image not found
```bash
# Verify image in ACR
az acr repository list --name "$ACR_NAME"
az acr repository show-tags --repository "$PROJECT_NAME-agent" --name "$ACR_NAME"
```

---

## Rollback

To revert to previous deployment:

```bash
# Get previous image tag
az acr repository show-tags --repository "underwriter-briefing-agent" --name "$ACR_NAME"

# Update to previous image
az containerapp update \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-agent" \
  --image "$ACR_NAME.azurecr.io/underwriter-briefing-agent:previous-tag"
```

---

## Cost Estimation

| Service | Config | Monthly Cost |
|---------|--------|--------------|
| ACA Apps (Agent) | 0.5 CPU, 1GB RAM | ~$30-50 |
| ACA Jobs (Batch) | 1 CPU, 2GB RAM, 2x/day | ~$5-10 |
| ACR | Basic tier | ~$5 |
| **Total** | | **~$40-65** |

---

## Next Steps

1. ✅ Run `./deploy.sh`
2. ✅ Test agent frontend at public URL
3. ✅ Monitor first batch job execution
4. ✅ Adjust schedule/resources as needed
5. ✅ Set up monitoring/alerts in Azure Portal

---

## Files Created

- `Dockerfile.agent` - FastAPI agent containerization
- `Dockerfile.batch` - Batch job containerization
- `batch_job_orchestrator.py` - Main batch processing logic
- `deploy.sh` - Automated deployment script (this guide)

All credentials are injected via environment variables or Azure Keyvault secrets, NOT hardcoded.
