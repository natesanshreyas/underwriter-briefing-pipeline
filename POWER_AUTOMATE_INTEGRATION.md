# Power Automate Integration

Your agent can be triggered via **Power Automate** for end-to-end workflow automation.

## Use Case 1: Email → Briefing → Slack Notification

```
Trigger: Email arrives in shared mailbox
    ↓
Action 1: Call your API /ProcessEmail
    ↓
Action 2: Generate briefing with AI inferences
    ↓
Action 3: Send formatted briefing to Slack
    ↓
Action 4: Update Cosmos DB
```

---

## Use Case 2: Daily Digest via Teams

```
Trigger: Daily (9 AM)
    ↓
Action 1: Query all briefings from past 24 hours
    ↓
Action 2: Format as markdown table
    ↓
Action 3: Post to Teams channel with attachments
```

---

## Use Case 3: Broker-Triggered Report

```
Trigger: Button in Teams
    "📊 Show me Acme briefings"
    ↓
Action 1: Call GetBriefingsByCompany
    ↓
Action 2: Format as adaptive card
    ↓
Action 3: Display in Teams thread
```

---

## JSON Schema for Custom Connector

```json
{
  "swagger": "2.0",
  "info": {
    "title": "Underwriter Briefing Agent",
    "description": "Intelligent briefing generation and retrieval",
    "version": "1.0.0"
  },
  "host": "briefing-agent-backend.azurewebsites.net",
  "basePath": "/",
  "schemes": ["https"],
  "paths": {
    "/chat": {
      "post": {
        "summary": "Chat with briefing agent",
        "operationId": "ChatWithAgent",
        "parameters": [
          {
            "name": "body",
            "in": "body",
            "required": true,
            "schema": {
              "type": "object",
              "properties": {
                "messages": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "role": { "type": "string" },
                      "content": { "type": "string" }
                    }
                  }
                }
              }
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Agent response",
            "schema": {
              "type": "object",
              "properties": {
                "message": {
                  "type": "object",
                  "properties": {
                    "role": { "type": "string" },
                    "content": { "type": "string" }
                  }
                },
                "function_calls": {
                  "type": "array"
                }
              }
            }
          }
        }
      }
    }
  }
}
```

---

## Teams Adaptive Card Example

```json
{
  "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
  "type": "AdaptiveCard",
  "version": "1.4",
  "body": [
    {
      "type": "TextBlock",
      "text": "📊 Underwriter Briefing",
      "weight": "bolder",
      "size": "large"
    },
    {
      "type": "TextBlock",
      "text": "Shreyas @ Acme Manufacturing",
      "weight": "bolder"
    },
    {
      "type": "Container",
      "items": [
        {
          "type": "TextBlock",
          "text": "**Sentiment:** Positive (74%)",
          "wrap": true
        },
        {
          "type": "TextBlock",
          "text": "**Status:** Requires underwriting review",
          "wrap": true
        }
      ],
      "style": "accent"
    },
    {
      "type": "ActionSet",
      "actions": [
        {
          "type": "Action.OpenUrl",
          "title": "View Full Report",
          "url": "https://your-app.com/briefing/shreyas_acme_com"
        },
        {
          "type": "Action.OpenUrl",
          "title": "Open in Cosmos DB",
          "url": "https://portal.azure.com/..."
        }
      ]
    }
  ]
}
```

---

## Quick Deploy to Teams

1. **Create Power Automate flow:**
   - Search "Cloud flows" → "Cloud flows"
   - New flow → "Automated cloud flow"
   - Trigger: "When a message is posted in a chat"

2. **Add actions:**
   - "Call your API" (via custom connector)
   - "Parse JSON" (response)
   - "Post message in chat" (formatted)

3. **Test with button trigger:**
   - Users click button in Teams
   - Agent generates briefing
   - Report appears in Teams thread

---

## Cost-Effective Alternative to Copilot Studio

| Solution | Cost | Effort | Customization |
|----------|------|--------|---------------|
| Copilot Studio (native) | $50+/mo | High | Low |
| **Your Agent** | $0-20/mo | Low | **High** |
| Teams Bot Framework | $30+/mo | Medium | Medium |

You're already winning! 🏆
