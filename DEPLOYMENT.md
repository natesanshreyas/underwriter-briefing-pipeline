# Deployment Guide - Underwriter Briefing System

## Prerequisites

1. **Azure CLI** installed and logged in:
   ```bash
   az login
   ```

2. **Azure Functions Core Tools** installed:
   ```bash
   # Install via npm
   npm install -g azure-functions-core-tools@4 --unsafe-perm true
   
   # Or via package manager (Ubuntu/Debian)
   wget -q https://packages.microsoft.com/config/ubuntu/20.04/packages-microsoft-prod.deb
   sudo dpkg -i packages-microsoft-prod.deb
   sudo apt-get update
   sudo apt-get install azure-functions-core-tools-4
   ```

3. **Python 3.11** installed

---

## Step 1: Create Cosmos DB Account

```bash
# Set variables
RESOURCE_GROUP="UnderwriterBriefingRG"
LOCATION="eastus"
COSMOS_ACCOUNT="underwriter-cosmos-db"

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create Cosmos DB account (serverless for cost efficiency)
az cosmosdb create \
  --name $COSMOS_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --locations regionName=$LOCATION \
  --capabilities EnableServerless \
  --kind GlobalDocumentDB

# Get connection details
COSMOS_ENDPOINT=$(az cosmosdb show --name $COSMOS_ACCOUNT --resource-group $RESOURCE_GROUP --query documentEndpoint -o tsv)
COSMOS_KEY=$(az cosmosdb keys list --name $COSMOS_ACCOUNT --resource-group $RESOURCE_GROUP --query primaryMasterKey -o tsv)

echo "Cosmos Endpoint: $COSMOS_ENDPOINT"
echo "Cosmos Key: $COSMOS_KEY"
```

**Update `secrets.json` and `local.settings.json` with these values:**
```json
{
  "COSMOS_ENDPOINT": "https://your-cosmos.documents.azure.com:443/",
  "COSMOS_KEY": "your-primary-key-here"
}
```

---

## Step 2: Test Cosmos DB Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Test connection
python3 cosmos_storage.py
```

You should see:
```
✅ Connected successfully!
📦 Database: UnderwriterDB
📦 Container: Briefings
✨ Cosmos DB integration ready!
```

---

## Step 3: Update Underwriter Script to Store in Cosmos

Add to the `__main__` block in `underwriter_briefing.py`:

```python
# Store in Cosmos DB
from cosmos_storage import BriefingStorage, get_cosmos_config

cosmos_cfg = get_cosmos_config()
if cosmos_cfg["endpoint"] and cosmos_cfg["key"]:
    storage = BriefingStorage(
        endpoint=cosmos_cfg["endpoint"],
        key=cosmos_cfg["key"]
    )
    stored = storage.store_briefing(briefing.to_dict())
    print(f"✅ Stored in Cosmos DB: {stored['id']}")
```

---

## Step 4: Test Azure Function Locally

```bash
# Start the function app
func start
```

You should see:
```
Functions:
  GetBriefing: [GET] http://localhost:7071/api/GetBriefing
  GetBriefingsByEmail: [GET] http://localhost:7071/api/GetBriefingsByEmail
  GetBriefingsByCompany: [GET] http://localhost:7071/api/GetBriefingsByCompany
  SearchBriefings: [GET] http://localhost:7071/api/SearchBriefings
  ProcessEmail: [POST] http://localhost:7071/api/ProcessEmail
```

**Test endpoints:**
```bash
# Process an email
curl -X POST http://localhost:7071/api/ProcessEmail \
  -H "Content-Type: application/json" \
  -d '{
    "email": "broker@company.com",
    "name": "John Doe",
    "company": "Acme Corp",
    "subject": "Renewal quote needed",
    "body": "Hi, we need a renewal quote for our GL policy..."
  }'

# Get briefings by email
curl "http://localhost:7071/api/GetBriefingsByEmail?email=broker@company.com"

# Search briefings
curl "http://localhost:7071/api/SearchBriefings?q=renewal&limit=5"
```

---

## Step 5: Deploy to Azure

```bash
# Set variables
FUNCTION_APP_NAME="underwriter-briefing-api"
STORAGE_ACCOUNT="underwriterstorage$(date +%s)"

# Create storage account for function app
az storage account create \
  --name $STORAGE_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard_LRS

# Create function app (Python 3.11)
az functionapp create \
  --resource-group $RESOURCE_GROUP \
  --name $FUNCTION_APP_NAME \
  --storage-account $STORAGE_ACCOUNT \
  --consumption-plan-location $LOCATION \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --os-type Linux

# Configure app settings
az functionapp config appsettings set \
  --name $FUNCTION_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings \
    LANGUAGE_ENDPOINT="https://<your-language-resource>.cognitiveservices.azure.com/" \
    OPENAI_ENDPOINT="https://<your-openai-resource>.openai.azure.com/" \
    OPENAI_MODEL="gpt-4o-mini" \
    COSMOS_ENDPOINT="https://<your-cosmos>.documents.azure.com:443/" \
    COSMOS_DATABASE="UnderwriterDB" \
    COSMOS_CONTAINER="Briefings"
# Note: No LANGUAGE_KEY, OPENAI_API_KEY, or COSMOS_KEY — authentication uses Managed Identity.

# Deploy the function
func azure functionapp publish $FUNCTION_APP_NAME --python

# Get the function URL
FUNCTION_URL=$(az functionapp show --name $FUNCTION_APP_NAME --resource-group $RESOURCE_GROUP --query defaultHostName -o tsv)
echo "Function App URL: https://$FUNCTION_URL"
```

---

## Step 6: Get Function Keys

```bash
# Get the function key (for authentication)
FUNCTION_KEY=$(az functionapp keys list --name $FUNCTION_APP_NAME --resource-group $RESOURCE_GROUP --query functionKeys.default -o tsv)

echo "Function Key: $FUNCTION_KEY"
echo ""
echo "API Endpoints:"
echo "  ProcessEmail:         https://$FUNCTION_URL/api/ProcessEmail?code=$FUNCTION_KEY"
echo "  GetBriefingsByEmail:  https://$FUNCTION_URL/api/GetBriefingsByEmail?code=$FUNCTION_KEY&email=<email>"
echo "  GetBriefingsByCompany: https://$FUNCTION_URL/api/GetBriefingsByCompany?code=$FUNCTION_KEY&company=<company>"
echo "  SearchBriefings:      https://$FUNCTION_URL/api/SearchBriefings?code=$FUNCTION_KEY&q=<query>"
```

---

## Step 7: Test Production Endpoint

```bash
# Process a test email
curl -X POST "https://$FUNCTION_URL/api/ProcessEmail?code=$FUNCTION_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "shreyas@acme.com",
    "name": "Shreyas",
    "company": "Acme Manufacturing",
    "subject": "Renewal quote",
    "body": "We need a renewal quote for our policy..."
  }'

# Retrieve briefings
curl "https://$FUNCTION_URL/api/GetBriefingsByEmail?code=$FUNCTION_KEY&email=shreyas@acme.com"
```

---

## Step 8: Connect to Copilot Studio

1. **Create Power Automate Flow:**
   - Trigger: When email arrives (Outlook)
   - Action: HTTP - Call ProcessEmail endpoint
   - Action: Parse JSON response
   - Action: Post to Copilot Studio (adaptive card)

2. **Copilot Studio Integration:**
   - Create topic: "Show briefing for [email]"
   - Action: Call GetBriefingsByEmail API
   - Display: Format as adaptive card

---

## Cost Estimate

**Per 1000 emails/day:**
- Cosmos DB (serverless): ~$5/month (400 RU/s, 10 GB)
- Azure Functions (consumption): ~$2/month
- Language Service: ~$4/month
- OpenAI (gpt-4o-mini): ~$8/month

**Total: ~$19/month for 1000 emails/day**

---

## Monitoring

```bash
# View logs
func azure functionapp logstream $FUNCTION_APP_NAME

# View metrics in Azure Portal
az monitor metrics list \
  --resource "/subscriptions/<subscription-id>/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Web/sites/$FUNCTION_APP_NAME" \
  --metric "Requests"
```

---

## Troubleshooting

**Function not deploying?**
```bash
# Check Python version
python3 --version  # Must be 3.11

# Reinstall dependencies
pip install -r requirements.txt

# Try manual deployment
func azure functionapp publish $FUNCTION_APP_NAME --python --build remote
```

**Cosmos DB connection failing?**
```bash
# Verify endpoint and key
python3 cosmos_storage.py

# Check firewall rules in Azure Portal
az cosmosdb update --name $COSMOS_ACCOUNT --resource-group $RESOURCE_GROUP --enable-public-network
```

---

## Next Steps

- [ ] Set up Application Insights for monitoring
- [ ] Configure CORS for web access
- [ ] Add batch processing (ACA Container Jobs)
- [ ] Set up CI/CD pipeline (GitHub Actions)
- [ ] Add authentication (Entra ID)
