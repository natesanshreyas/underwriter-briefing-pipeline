# 🚀 Quick Deployment to Azure

## Summary: Your Options

| Where | Effort | Cost | Time |
|-------|--------|------|------|
| **Local Testing** | ✅ Done | $0 | Running now |
| **Deploy to Azure** | 20 min | $50-150/mo | Today |
| **Copilot Studio Integration** | 30 min | $0 (free connector) | Today |
| **Teams Bot** | 45 min | $0 | Today |
| **Production at Scale** | 2 hrs | Minimal | This week |

---

## Option 1: Deploy Backend to Azure (Recommended First Step)

### What gets deployed:
- Your FastAPI agent backend
- Auto-scales with traffic
- Runs 24/7

### Commands:

```bash
cd /home/snatesan/projects/graphapp_onedrive

# 1. Create resource group
az group create \
  --name briefing-agent-rg \
  --location eastus2

# 2. Create App Service plan
az appservice plan create \
  --name briefing-agent-plan \
  --resource-group briefing-agent-rg \
  --sku B1 --is-linux

# 3. Create web app
az webapp create \
  --resource-group briefing-agent-rg \
  --plan briefing-agent-plan \
  --name briefing-agent-backend \
  --runtime "PYTHON:3.11"

# 4. Configure for FastAPI
az webapp config set \
  --resource-group briefing-agent-rg \
  --name briefing-agent-backend \
  --startup-file "python -m uvicorn ai_agent_backend:app --host 0.0.0.0 --port 8000"

# 5. Set environment variables (CRITICAL!)
az webapp config appsettings set \
  --resource-group briefing-agent-rg \
  --name briefing-agent-backend \
  --settings \
    OPENAI_ENDPOINT="https://<your-openai-resource>.openai.azure.com/" \
# Note: No OPENAI_API_KEY — authentication uses Managed Identity.
    OPENAI_MODEL="gpt-4o-mini" \
    AZURE_FUNCTIONS_BASE_URL="https://underwriter-briefing-api.azurewebsites.net/api"

# 6. Deploy code
az webapp deployment source config-zip \
  --resource-group briefing-agent-rg \
  --name briefing-agent-backend \
  --src <(zip -r - . -x ".git/*" "__pycache__/*" ".env*")

# 7. Check it's running
curl https://briefing-agent-backend.azurewebsites.net/
# Should return: {"status": "running", ...}
```

**Result:**
- Backend running at: `https://briefing-agent-backend.azurewebsites.net`
- Cost: ~$50/month

---

## Option 2: Deploy Frontend to Static Web Apps (Free)

```bash
# 1. Create Static Web App
az staticwebapp create \
  --name briefing-agent-frontend \
  --resource-group briefing-agent-rg \
  --source ./frontend \
  --location eastus2 \
  --branch main

# 2. Update frontend to use production backend
# Edit frontend/index.html line ~237:
# Change: const API_BASE_URL = 'http://localhost:8000'
# To: const API_BASE_URL = 'https://briefing-agent-backend.azurewebsites.net'

# 3. Commit and push
git add .
git commit -m "Update API endpoint for production"
git push origin main

# Frontend auto-deploys and is live!
```

**Result:**
- Frontend running at: auto-generated Azure URL (free!)

---

## Option 3: Copilot Studio Integration (30 min)

1. **Go to:** https://web.copilot.microsoft.com
2. **Create project**
3. **Settings → Custom Connectors → Create**
4. **Configure:**
   - Name: "Underwriter Briefing Agent"
   - Base URL: `https://briefing-agent-backend.azurewebsites.net`
   - Operations: Import Swagger (use json below)
5. **Create topic:**
   - Trigger: "Show briefings for {company}"
   - Action: Call connector /chat endpoint
6. **Test → Publish**

### Swagger for Custom Connector:

```yaml
openapi: 3.0.0
info:
  title: Underwriter Briefing Agent
  version: 1.0.0
paths:
  /chat:
    post:
      summary: Chat with agent
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                messages:
                  type: array
                  items:
                    properties:
                      role:
                        type: string
                      content:
                        type: string
      responses:
        '200':
          description: Agent response
          content:
            application/json:
              schema:
                type: object
```

---

## Option 4: Full Production Stack (Multi-Region)

Use **Azure Container Apps** for true serverless:

```bash
# Create container app environment
az containerapp env create \
  --name briefing-agent-env \
  --resource-group briefing-agent-rg \
  --location eastus2

# Deploy container
az containerapp create \
  --name briefing-agent \
  --resource-group briefing-agent-rg \
  --environment briefing-agent-env \
  --image briefing-agent-backend:latest \
  --target-port 8000 \
  --ingress external \
  --env-vars \
    OPENAI_API_KEY=$OPENAI_API_KEY \
    OPENAI_ENDPOINT=$OPENAI_ENDPOINT \
    AZURE_FUNCTIONS_BASE_URL="https://underwriter-briefing-api.azurewebsites.net/api"

# Cost: ~$15-20/month (auto-scales)
```

---

## Recommended Path

### Week 1:
- [ ] ✅ Agent working locally (you're here!)
- [ ] Deploy backend to App Service (30 min)
- [ ] Deploy frontend to Static Web Apps (10 min)
- [ ] Test end-to-end on Azure

### Week 2:
- [ ] Create Copilot Studio custom connector
- [ ] Create topic with sample queries
- [ ] Get stakeholder feedback

### Week 3:
- [ ] Publish to Copilot Studio
- [ ] Enable for your org
- [ ] Monitor with Application Insights

---

## Estimated Timeline & Cost

| Milestone | Effort | Cost |
|-----------|--------|------|
| Deploy backend | 20 min | $50/mo |
| Deploy frontend | 10 min | $0 |
| Copilot integration | 30 min | $0 |
| **Go Live** | **1 hour** | **$50/mo** |
| Monitor + optimize | 1 week | Included |

---

## Architecture After Deployment

```
Users (Web/Teams/Copilot)
        ↓
Copilot Studio / Static Web App
        ↓
App Service (FastAPI backend)
        ↓
Azure OpenAI (GPT-4)
        ↓
Azure Functions (Your API)
        ↓
Cosmos DB (Briefings)
```

All Azure-native, all monitored, all scalable ✅

---

## Health Checks

After deploying, verify:

```bash
# Backend health
curl https://briefing-agent-backend.azurewebsites.net/

# Config
curl https://briefing-agent-backend.azurewebsites.net/config | jq .

# Test chat
curl -X POST https://briefing-agent-backend.azurewebsites.net/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Show briefings for Acme"}]}'
```

---

## Stop or Troubleshoot

```bash
# Stop the app (free up costs)
az webapp stop -g briefing-agent-rg -n briefing-agent-backend

# View logs
az webapp log tail -g briefing-agent-rg -n briefing-agent-backend

# Scale up if needed
az appservice plan update -g briefing-agent-rg --name briefing-agent-plan --sku S1

# Restart
az webapp restart -g briefing-agent-rg -n briefing-agent-backend
```

---

## Next: Which would you like to do?

1. **Deploy to Azure now** (I'll run the commands)
2. **Test locally more first** (fine, take your time!)
3. **Set up Copilot Studio integration** (after deployment)
4. **All of the above** (let's go!)
