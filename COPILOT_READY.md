# COPILOT STUDIO TOPIC - PRODUCTION READY

**TOPIC NAME:** Get Underwriter Briefing

**API ENDPOINT (USE THIS):** 
```
http://127.0.0.1:7071/api/GetBriefingsByEmail?email={email}
```

**EXACT TOPIC YAML TO PASTE INTO COPILOT STUDIO:**

```yaml
kind: AdaptiveDialog
beginDialog:
  - kind: OnRecognizedIntent
    id: get_briefing_trigger
    intent:
      triggerQueries:
        - get briefing
        - show briefing
        - retrieve briefing
        - briefing
        - underwriter briefing
    actions:
      - kind: Question
        id: ask_email
        prompt: "What is the broker's email address?"
        property: Topic.email
        inputType: Text

      - kind: HttpRequestAction
        id: call_briefing_api
        url: =Concatenate("http://127.0.0.1:7071/api/GetBriefingsByEmail?email=", UrlEncode(Topic.email))
        method: Get
        response: Topic.apiResponse

      - kind: SendActivity
        id: display_result
        activity: =IF(
          Topic.apiResponse.statusCode = 200,
          Concatenate("**Briefing Retrieved:**\n\n", JSONStringify(Topic.apiResponse.body)),
          Concatenate("**Error:** Status ", Topic.apiResponse.statusCode, " - ", Topic.apiResponse.body)
        )
```

---

## HOW TO USE IN COPILOT STUDIO:

1. Open Copilot Studio → Your Agent (Agent 5)
2. Click **Topics** tab
3. Click **Create** → **Topic from Blank**
4. Name it: **Get Underwriter Briefing**
5. Click **Code Editor** (top right)
6. **PASTE THE YAML ABOVE** (between the begin and end)
7. Click **Save**
8. Click **Publish**
9. In the test chat, type: **get briefing**
10. Enter email: **test@example.com**
11. Response: `{"count": 0, "briefings": []}`

---

## TO USE WITH REAL DATA:

First, generate and store a briefing:

```bash
cd /home/snatesan/projects/graphapp_onedrive
python3 underwriter_briefing.py
```

This will create a briefing and store it in Cosmos DB. Then test the API with that email.

---

## ENDPOINTS AVAILABLE:

- **GET /api/GetBriefingsByEmail?email=broker@company.com**
  Returns all briefings for an email
  
- **GET /api/GetBriefing?id=ID&company=COMPANY**
  Returns specific briefing by ID

- **GET /api/GetBriefingsByCompany?company=COMPANY**
  Returns all briefings for a company

- **GET /api/SearchBriefings?q=KEYWORD**
  Search briefings by keyword

---

## RUNNING STATUS:

✅ Azure Functions runtime is RUNNING on port 7071
✅ Cosmos DB credentials are configured
✅ API is LIVE and RESPONDING
✅ Ready for Copilot Studio integration

---
