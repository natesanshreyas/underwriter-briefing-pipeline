# Quick Start: Cosmos DB + Copilot Studio Setup

## What We're Building

A complete flow:
```
Broker Email → Extraction Layer → LLM Narrative → Cosmos DB → Copilot Studio Chat
```

---

## Part 1: Cosmos DB Setup (15 minutes)

### 1.1 Create Cosmos DB Account

```bash
# Azure CLI
az cosmosdb create \
  --name insurance-briefings-db \
  --resource-group my-resource-group \
  --kind GlobalDocumentDB
```

Or via Azure Portal:
- Create resource → "Azure Cosmos DB"
- Select "Core (SQL)" API
- Set account name, region
- Review + Create

### 1.2 Create Database & Container

```bash
az cosmosdb sql database create \
  --account-name insurance-briefings-db \
  --resource-group my-resource-group \
  --name insurance_db

az cosmosdb sql container create \
  --account-name insurance-briefings-db \
  --database-name insurance_db \
  --name briefings \
  --partition-key-path "/metadata/broker_company" \
  --throughput 400
```

**Partition Key Note:** Using `broker_company` allows efficient queries by company (e.g., "Show all briefings from Acme Manufacturing")

### 1.3 Get Connection String

```bash
az cosmosdb keys list \
  --name insurance-briefings-db \
  --resource-group my-resource-group \
  --type connection-strings
```

Add to `secrets.json`:
```json
{
  "COSMOS_CONNECTION_STRING": "AccountEndpoint=https://insurance-briefings-db.documents.azure.com:443/;AccountKey=..."
}
```

---

## Part 2: Python Script Integration (20 minutes)

### 2.1 Install Cosmos DB SDK

```bash
pip install azure-cosmos
```

Update `requirements.txt`:
```
azure-ai-textanalytics>=5.3.0
azure-cosmos>=4.4.0
openai>=1.0.0
```

### 2.2 Add Cosmos Storage to Script

Create `cosmos_helper.py`:

```python
"""Cosmos DB helpers for briefing storage."""
from azure.cosmos import CosmosClient, PartitionKey
from datetime import datetime
import json

class BriefingStorage:
    def __init__(self, connection_string: str):
        self.client = CosmosClient.from_connection_string(connection_string)
        self.database = self.client.get_database_client("insurance_db")
        self.container = self.database.get_container_client("briefings")
    
    def store_briefing(self, briefing_dict: dict) -> dict:
        """Store briefing in Cosmos DB, return the stored document."""
        # Add system metadata
        document = {
            "id": f"briefing-{briefing_dict['metadata']['broker_email']}-{datetime.now().isoformat()}",
            "partitionKey": briefing_dict['metadata']['broker_company'],
            "createdAt": datetime.now().isoformat(),
            **briefing_dict
        }
        
        # Store
        response = self.container.create_item(body=document)
        print(f"✅ Stored briefing: {document['id']}")
        return response
    
    def get_latest_briefing(self, broker_email: str) -> dict:
        """Retrieve most recent briefing for a broker."""
        query = """
            SELECT TOP 1 * FROM c 
            WHERE c.metadata.broker_email = @email 
            ORDER BY c.createdAt DESC
        """
        params = [{"name": "@email", "value": broker_email}]
        results = list(self.container.query_items(query, params))
        return results[0] if results else None
    
    def get_briefings_by_company(self, company: str, limit: int = 10) -> list:
        """Get recent briefings for a company."""
        query = f"""
            SELECT TOP {limit} * FROM c 
            WHERE c.partitionKey = @company 
            ORDER BY c.createdAt DESC
        """
        params = [{"name": "@company", "value": company}]
        return list(self.container.query_items(query, params))
    
    def search_briefings(self, sentiment: str = None, min_confidence: float = 0.5) -> list:
        """Search briefings by criteria."""
        query = """
            SELECT * FROM c 
            WHERE c.sections['2_sentiment_and_tone'].overall_sentiment = @sentiment 
            AND c.sections['10_confidence_and_limitations'].overall_confidence >= @confidence
            ORDER BY c.createdAt DESC
        """
        params = [
            {"name": "@sentiment", "value": sentiment},
            {"name": "@confidence", "value": min_confidence}
        ]
        return list(self.container.query_items(query, params))
```

### 2.3 Update Main Script

```python
# In underwriter_briefing.py __main__ block

from cosmos_helper import BriefingStorage
import os

# ... existing extraction code ...

# Initialize storage
cosmos_conn_str = cfg.get("COSMOS_CONNECTION_STRING")
if cosmos_conn_str:
    storage = BriefingStorage(cosmos_conn_str)
    
    # Store briefing
    storage.store_briefing(briefing.to_dict())
    
    # Retrieve to verify
    retrieved = storage.get_latest_briefing(briefing.broker_email)
    print(f"✅ Retrieved from Cosmos: {retrieved['id']}")
else:
    print("⚠️ COSMOS_CONNECTION_STRING not configured (optional)")
```

---

## Part 3: Azure Function API (30 minutes)

### 3.1 Create Azure Function

```bash
# Create function project
func init insurance-briefing-api --python

cd insurance-briefing-api

# Create HTTP-triggered function
func new --name GetBriefing --template "HTTP trigger"
```

### 3.2 Implement API Endpoint

Replace `insurance_briefing_api/GetBriefing/function_app.py`:

```python
import azure.functions as func
from cosmos_helper import BriefingStorage
import json
import os

def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get latest briefing for a broker email.
    
    Query: GET /GetBriefing?email=shreyas@acme.com
    Returns: 200 {narrative, sections, metadata}
            404 if not found
    """
    
    email = req.params.get('email')
    if not email:
        return func.HttpResponse("Missing 'email' parameter", status_code=400)
    
    try:
        # Initialize storage
        storage = BriefingStorage(os.getenv("COSMOS_CONNECTION_STRING"))
        
        # Retrieve briefing
        briefing = storage.get_latest_briefing(email)
        
        if not briefing:
            return func.HttpResponse(
                json.dumps({"error": "No briefing found for " + email}),
                status_code=404,
                mimetype="application/json"
            )
        
        # Extract narrative + key sections for chat display
        response_body = {
            "displayName": f"{briefing['metadata']['broker_name']} ({briefing['metadata']['broker_company']})",
            "narrative": briefing['metadata'].get('narrative_summary', 'No narrative available'),
            "sentiment": briefing['sections']['2_sentiment_and_tone']['overall_sentiment'],
            "confidence": briefing['sections']['10_confidence_and_limitations']['overall_confidence'],
            "generatedAt": briefing.get('createdAt'),
            "fullBriefing": briefing  # Include full JSON for detailed view
        }
        
        return func.HttpResponse(
            json.dumps(response_body, indent=2),
            status_code=200,
            mimetype="application/json"
        )
    
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
```

### 3.3 Deploy Function

```bash
# Add function app settings
func azure functionapp config appsettings set \
  --name insurance-api-func \
  --setting COSMOS_CONNECTION_STRING=$COSMOS_CONN_STR

# Deploy to Azure
func azure functionapp publish insurance-api-func
```

---

## Part 4: Copilot Studio Integration (20 minutes)

### 4.1 Create Power Automate Flow

In Power Automate:

1. **Create Cloud Flow → Cloud flows → Automated cloud flow**
2. **Trigger:** "When a new email arrives in a shared mailbox" (Outlook)
3. **Add Action:** "Initialize variable"
   - Name: `brokerEmail`
   - Value: `From (dynamic content from trigger)`

4. **Add Action:** "HTTP"
   - Method: `GET`
   - URI: `https://insurance-api-func.azurewebsites.net/api/GetBriefing?email=@{variables('brokerEmail')}`
   - Authentication: Function Key
   - Headers: `Content-Type: application/json`

5. **Add Action:** "Parse JSON"
   - Content: output from HTTP action
   - Schema: (auto-generate from sample response)

6. **Add Action:** "Send an HTTP request to Power Automate"
   - Send notification to Copilot Studio

### 4.2 Connect to Copilot Studio

In **Copilot Studio** (Power Virtual Agents):

1. Create new topic: "Request Briefing"
2. Trigger phrases:
   - "Brief me on {email}"
   - "Show me briefing for {email}"
   - "What's my briefing"

3. Actions:
   ```
   User says: "Brief me on shreyas@acme.com"
   
   → Call Power Automate flow
   → Receive briefing JSON
   → Display card:
      Broker: Shreyas (Acme Mfg)
      Sentiment: Positive (92%)
      
      [Narrative from LLM]
      "Shreyas from Acme Manufacturing has reached out 
       regarding their policy renewal with a clear 
       collaborative tone..."
      
      Key Risks: Time pressure, Competitive positioning
      Next Steps: Confirm coverage limits, Provide quote
      
      [View Full Briefing] [Share with Team]
   ```

---

## Part 5: Test End-to-End (10 minutes)

### 5.1 Local Testing

```bash
# 1. Set environment variables
export COSMOS_CONNECTION_STRING="..."
export OPENAI_API_KEY="..."
export OPENAI_ENDPOINT="..."

# 2. Run script
python3 underwriter_briefing.py

# Expected output:
# ✅ Stored briefing: briefing-shreyas@acme.com-2024-01-31T10:30:00Z
# ✅ Retrieved from Cosmos: briefing-shreyas@acme.com-2024-01-31T10:30:00Z
```

### 5.2 Test API Endpoint

```bash
curl "https://insurance-api-func.azurewebsites.net/api/GetBriefing?email=shreyas@acme.com"

# Expected response:
# {
#   "displayName": "Shreyas (Acme Manufacturing)",
#   "narrative": "Shreyas from Acme Manufacturing...",
#   "sentiment": "Positive",
#   "confidence": 0.78,
#   "generatedAt": "2024-01-31T10:30:00Z",
#   "fullBriefing": { ... }
# }
```

### 5.3 Test Copilot Studio

In Copilot Studio chat:
```
User: "Brief me on shreyas@acme.com"

Bot: 
  → Calls Power Automate flow
  → Retrieves briefing
  → Displays: "Shreyas (Acme Manufacturing)"
  → Shows LLM narrative
  → Offers drill-down options
```

---

## Part 6: Configuration Checklist

### Secrets to Configure

Add to `secrets.json`:

```json
{
  "LANGUAGE_ENDPOINT": "https://xxx.cognitiveservices.azure.com/",
  "LANGUAGE_KEY": "...",
  "COSMOS_CONNECTION_STRING": "AccountEndpoint=...",
  "OPENAI_API_KEY": "...",
  "OPENAI_ENDPOINT": "https://xxx.openai.azure.com/",
  "OPENAI_MODEL": "gpt-3.5-turbo"
}
```

### Azure Permissions

Ensure your service principal/account has:
- ✅ Cosmos DB Contributor
- ✅ Cognitive Services User
- ✅ Azure Function Contributor
- ✅ Azure App Service Plan Contributor

---

## Part 7: Monitoring & Alerts

### Application Insights Queries

```kusto
# 1. Briefings processed per day
customEvents
| where name == "briefing_stored"
| summarize count() by bin(timestamp, 1d)

# 2. LLM narrative generation latency
customMetrics
| where name == "narrative_generation_ms"
| summarize avg(value), max(value) by bin(timestamp, 1h)

# 3. API errors
requests
| where url contains "GetBriefing" and success == false
| summarize count() by resultCode
```

### Alerts

Set up alerts for:
- ⚠️ Cosmos DB throughput exceeding 80%
- ⚠️ API response time > 2 seconds
- ⚠️ LLM generation failures
- ⚠️ Cosmos DB query costs > threshold

---

## Summary: What You Get

✅ **Structured Data:** All 10 briefing sections in Cosmos DB  
✅ **Searchable:** Query by sentiment, confidence, broker company  
✅ **API-Driven:** RESTful access for any application  
✅ **Copilot Integrated:** Chat-based briefing retrieval  
✅ **Auditable:** Full JSON trail stored forever  
✅ **Scalable:** Partition key on company allows growth to millions  
✅ **Cost-Transparent:** Pay for what you query  

**Total setup time:** ~90 minutes  
**Cost to run (100 emails/day):** ~$30-40/month
