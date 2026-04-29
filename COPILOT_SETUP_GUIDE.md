# COPILOT STUDIO TOPIC - COMPLETE WORKING SETUP
# ============================================================================
# 
# PROBLEM: Your current topic isn't triggering properly
# SOLUTION: Use this exact topic definition
#
# ============================================================================

**TOPIC NAME:** "Get Underwriter Briefing"

**TRIGGER PHRASES:**
- get briefing
- show briefing
- retrieve briefing
- briefing
- underwriter briefing
- get underwriter briefing

**TOPIC FLOW:**

1. **User Input (Required)**
   - Ask: "What is the broker's email address?"
   - Save to: Topic.email
   - Type: Text input

2. **Call API**
   - Method: GET
   - URL: https://underwriter-briefing-api.azurewebsites.net/api/GetBriefingsByEmail?email={Topic.email}
   - Save response to: Topic.apiResult
   - Headers: Content-Type: application/json

3. **Check Success**
   - IF: Topic.apiResult.statusCode = 200
   - THEN: Show: Topic.apiResult.body (formatted as code/JSON)

4. **Handle Error**
   - IF: Topic.apiResult.statusCode ≠ 200
   - THEN: Show error message with status code

---

# YAML FOR COPY-PASTE:

kind: AdaptiveDialog
beginDialog:
  - kind: OnRecognizedIntent
    id: unw_trigger
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
        id: call_api
        url: =Concatenate("https://underwriter-briefing-api.azurewebsites.net/api/GetBriefingsByEmail?email=", UrlEncode(Topic.email))
        method: Get
        response: Topic.result

      - kind: SendActivity
        id: show_result
        activity: =IF(Topic.result.statusCode = 200, 
          Concatenate("**Briefing Retrieved:**\n\n", JSONStringify(Topic.result.body)), 
          Concatenate("**Error**: Status ", Topic.result.statusCode, " - ", Topic.result.body))

---

# TROUBLESHOOTING:

IF YOU STILL GET "Sorry, I am not able to find a related topic":
  ✓ Make sure the topic is SAVED
  ✓ Make sure you PUBLISHED the agent
  ✓ Try saying exact trigger phrase: "get briefing"
  ✓ Wait 30 seconds after publishing
  ✓ Try in a new chat/test window

IF API RETURNS 500 ERROR:
  ✓ Check that Cosmos DB credentials are set in Azure Function settings
  ✓ Verify the function app is deployed
  ✓ Check function logs in Azure Portal

IF API RETURNS 404:
  ✓ Email doesn't have any briefings stored
  ✓ Try: shreyas@acme.com (test email from the code)
  ✓ First generate a briefing and store it in Cosmos DB

IF YOU SEE JSON BUT IT'S NOT FORMATTED:
  ✓ Add this action after the show_result action:
    - kind: SendActivity
      activity: =Concatenate("```json\n", JSONStringify(Topic.result.body, 2), "\n```")

---
