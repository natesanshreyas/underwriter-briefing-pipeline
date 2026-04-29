# Quick Start: Deploy Underwriter Briefing System

## 📋 Pre-Deployment Checklist

- [ ] Azure CLI installed (`az --version`)
- [ ] Docker running (`docker ps`)
- [ ] Logged into Azure (`az login`)
- [ ] ACA extension installed (`az extension add -n containerapp`)
- [ ] Have all credentials from `secrets.json` or environment

## 🚀 Deployment Steps (5 minutes)

### 1. Create Azure Container Registry
```bash
ACR_NAME="shreyas123"  # CHANGE THIS to something unique
RESOURCE_GROUP="your-rg"  # Your existing resource group

az acr create --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --sku Basic
```

### 2. Update deploy.sh
Edit line 16-19 in `deploy.sh`:
```bash
RESOURCE_GROUP="your-rg"
ACR_NAME="shreyas123"
```

### 3. Export Credentials
```bash
export OPENAI_API_KEY="your-key"
export OPENAI_ENDPOINT="your-endpoint"
export LANGUAGE_ENDPOINT="your-endpoint"
export LANGUAGE_KEY="your-key"
export COSMOS_ENDPOINT="your-endpoint"
export COSMOS_KEY="your-key"
export GRAPH_TENANT_ID="your-tenant-id"
export GRAPH_CLIENT_ID="your-client-id"
export GRAPH_CLIENT_SECRET="your-secret"
```

Or from secrets.json:
```bash
source <(jq -r 'to_entries | .[] | "export \(.key)=\(.value)"' secrets.json)
```

### 4. Run Deploy Script
```bash
chmod +x deploy.sh
./deploy.sh
```

This will:
- Build 2 Docker images
- Push to ACR
- Deploy agent to ACA Apps (public URL)
- Deploy batch job to ACA Jobs (9am daily)

## ✅ After Deployment

### Get Agent URL
```bash
az containerapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-agent" \
  --query "properties.configuration.ingress.fqdn" -o tsv
```

Visit: `https://[YOUR-URL]`

### Monitor Agent Logs
```bash
az containerapp logs show \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-agent" \
  --follow
```

### Test Batch Job
```bash
# Manually trigger once to verify
az containerapp job start \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-batch"

# Check logs
az containerapp job logs show \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-batch"
```

## 📊 What You Get

| Component | Where | Purpose |
|-----------|-------|---------|
| **Agent Frontend** | ACA Apps | User-facing UI (24/7 running) |
| **Batch Job** | ACA Jobs | Email processing (scheduled 2x daily) |
| **API Backend** | Azure Functions | Already deployed ✅ |
| **Data Store** | Cosmos DB | Already deployed ✅ |

## 🔗 Architecture

```
User → Agent UI (ACA Apps 8080) → Azure Functions API → Cosmos DB
          ↑
          └── Batch Job (ACA Jobs) → Cosmos DB (2x daily)
```

## 💰 Estimated Cost
- ACA Apps: ~$30-50/month
- ACA Jobs: ~$5-10/month
- ACR: ~$5/month
- **Total: ~$40-65/month**

## 🆘 Troubleshooting

**Agent URL not responding?**
```bash
# Check status
az containerapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-agent" \
  --query "properties.provisioningState"
```

**Batch job not running?**
```bash
# Check schedule
az containerapp job show \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-batch" \
  --query "properties.configuration.triggerConfig"

# View execution history
az containerapp job execution list \
  --resource-group "$RESOURCE_GROUP" \
  --name "underwriter-briefing-batch"
```

**Image push failed?**
```bash
# Login to ACR
az acr login --name "$ACR_NAME"

# Retry deploy script
./deploy.sh
```

## 📖 Full Details
See `DEPLOYMENT_GUIDE.md` for complete instructions.
