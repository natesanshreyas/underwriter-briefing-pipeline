# 🚀 AI Foundry Agent Deployment Guide

## What You Have

A complete AI agent system with:
- **AI Agent Backend** (`ai_agent_backend.py`) - FastAPI server with function calling
- **Web Frontend** (`frontend/index.html`) - Beautiful chat interface
- **Agent Configuration** (`ai_agent_config.json`) - GPT-4 agent definition
- **Azure Functions Integration** - Calls your deployed API

## Architecture

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────────┐      ┌──────────────┐
│   Browser   │─────▶│  FastAPI Backend │─────▶│  Azure OpenAI   │─────▶│   Azure      │
│  (Frontend) │      │  (ai_agent_      │      │   (GPT-4 Agent) │      │  Functions   │
│             │◀─────│   backend.py)    │◀─────│                 │◀─────│     API      │
└─────────────┘      └──────────────────┘      └─────────────────┘      └──────────────┘
                              │
                              ▼
                     Function Calling:
                     - get_briefing()
                     - get_briefings_by_email()
```

## Quick Start (Local Development)

### 1. Install Dependencies

```bash
cd /home/snatesan/projects/graphapp_onedrive

# Install backend dependencies
pip install -r requirements_agent.txt
```

### 2. Configure Environment

Edit `.env.agent` with your credentials:

```bash
# Copy from your secrets.json
OPENAI_API_KEY=your-actual-key
OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
OPENAI_MODEL=gpt-4

# Your deployed Azure Function
AZURE_FUNCTIONS_BASE_URL=https://underwriter-briefing-api.azurewebsites.net/api
```

### 3. Start Backend

```bash
# Load environment variables
export $(cat .env.agent | xargs)

# Start FastAPI server
python ai_agent_backend.py
```

Expected output:
```
INFO:     Started server process [12345]
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 4. Open Frontend

```bash
# Open in browser (or use live server)
cd frontend
python -m http.server 3000
```

Then visit: `http://localhost:3000`

### 5. Test the Agent

Try these queries in the chat interface:

1. **"Show me briefings for shreyas@acme.com"**
   - Calls `get_briefings_by_email()`
   - Returns list of all briefings

2. **"Get briefing ID test_example_com_2026-01-31 for company Acme"**
   - Calls `get_briefing(id, company)`
   - Returns specific briefing

3. **"What are the urgent items?"**
   - Agent analyzes briefings and highlights priorities

## Production Deployment

### Option 1: Azure Container Apps (Recommended)

**Deploy Backend:**

```bash
# 1. Create container registry
az acr create --resource-group your-rg --name briefingagent --sku Basic

# 2. Build and push image
az acr build --registry briefingagent --image agent-backend:latest .

# 3. Create Container App
az containerapp create \
  --name briefing-agent-backend \
  --resource-group your-rg \
  --image briefingagent.azurecr.io/agent-backend:latest \
  --target-port 8000 \
  --ingress external \
  --env-vars \
    OPENAI_API_KEY=$OPENAI_API_KEY \
    OPENAI_ENDPOINT=$OPENAI_ENDPOINT \
    AZURE_FUNCTIONS_BASE_URL=$AZURE_FUNCTIONS_BASE_URL
```

**Deploy Frontend:**

```bash
# Option A: Azure Static Web Apps
az staticwebapp create \
  --name briefing-agent-frontend \
  --resource-group your-rg \
  --source frontend/ \
  --location eastus2

# Option B: Azure App Service
az webapp up \
  --name briefing-agent-frontend \
  --resource-group your-rg \
  --html
```

### Option 2: Azure App Service

```bash
# Deploy backend as App Service
az webapp up \
  --name briefing-agent-backend \
  --resource-group your-rg \
  --runtime "PYTHON:3.11" \
  --sku B1

# Configure app settings
az webapp config appsettings set \
  --name briefing-agent-backend \
  --resource-group your-rg \
  --settings \
    OPENAI_API_KEY=$OPENAI_API_KEY \
    OPENAI_ENDPOINT=$OPENAI_ENDPOINT \
    AZURE_FUNCTIONS_BASE_URL=$AZURE_FUNCTIONS_BASE_URL
```

### Option 3: Run in Azure AI Foundry Studio

Instead of deploying the backend, you can use Azure AI Foundry's built-in agent hosting:

1. **Go to Azure AI Foundry Studio**
   - Visit: https://ai.azure.com

2. **Create New Project**
   - Click "Create new project"
   - Select your subscription and resource group

3. **Create Agent**
   - Go to "Agents" → "Create"
   - Upload `ai_agent_config.json`
   - Configure function endpoints

4. **Deploy as Web App**
   - Click "Deploy" → "Web app"
   - Gets auto-generated frontend + backend

## Update Frontend for Production

Once deployed, update the API URL in `frontend/index.html`:

```javascript
// Line 237 - Update this
const API_BASE_URL = 'https://briefing-agent-backend.azurewebsites.net';
```

## Testing Function Calling

Test the backend directly:

```bash
# Test chat endpoint
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Show me briefings for shreyas@acme.com"}
    ]
  }'
```

Expected response includes:
```json
{
  "message": {
    "role": "assistant",
    "content": "Here are the briefings for shreyas@acme.com:\n\n..."
  },
  "function_calls": [
    {
      "name": "get_briefings_by_email",
      "arguments": {"email": "shreyas@acme.com", "limit": 10},
      "result": { ... }
    }
  ]
}
```

## Dockerfile (for Container Deployment)

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements_agent.txt .
RUN pip install --no-cache-dir -r requirements_agent.txt

COPY ai_agent_backend.py .
COPY ai_agent_config.json .

EXPOSE 8000

CMD ["uvicorn", "ai_agent_backend:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Monitoring

View logs:

```bash
# Container Apps
az containerapp logs show \
  --name briefing-agent-backend \
  --resource-group your-rg \
  --follow

# App Service
az webapp log tail \
  --name briefing-agent-backend \
  --resource-group your-rg
```

## Cost Estimate

- **Azure Container Apps**: ~$15/month (1 vCPU, 2GB RAM)
- **Azure Static Web Apps**: Free tier available
- **GPT-4 API Calls**: ~$0.03 per conversation (with function calling)
- **Azure Functions**: Already deployed ✅

**Total**: ~$15-20/month + per-use GPT-4 costs

## Troubleshooting

**Backend won't start:**
```bash
# Check dependencies
pip list | grep -E "fastapi|openai|httpx"

# Test configuration
python -c "from ai_agent_backend import load_agent_config; print(load_agent_config())"
```

**CORS errors in browser:**
- Update `allow_origins` in `ai_agent_backend.py` to include your frontend domain

**Function calls not working:**
- Verify Azure Functions URL is accessible
- Test manually: `curl https://underwriter-briefing-api.azurewebsites.net/api/GetBriefing?id=test&company=Acme`

## Next Steps

1. ✅ Test locally (localhost:8000 + localhost:3000)
2. 🚀 Deploy backend to Azure Container Apps
3. 🌐 Deploy frontend to Static Web Apps
4. 🔒 Add authentication (Azure AD)
5. 📊 Add telemetry (Application Insights)
6. 🎨 Customize UI branding

## Security Notes

- **Production**: Replace CORS `allow_origins=["*"]` with your frontend domain
- **Authentication**: Add Azure AD auth to both frontend and backend
- **API Keys**: Use Azure Key Vault for production secrets
- **Rate Limiting**: Add rate limiting to prevent abuse

---

Ready to deploy! 🎉
