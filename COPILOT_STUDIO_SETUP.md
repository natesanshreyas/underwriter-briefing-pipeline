# ============================================================================
# COPILOT STUDIO TOPIC - UNDERWRITER BRIEFING RETRIEVAL
# ============================================================================
#
# PURPOSE: Retrieve underwriter briefing JSON from Azure Function API
# TRIGGER: User says "get briefing" or related phrases
# ACTION: Call API, parse response, display structured briefing
#
# ============================================================================
# STEPS TO USE IN COPILOT STUDIO:
# ============================================================================
# 1. Go to Copilot Studio > Your Agent > Topics
# 2. Click "Create" and select "From Blank"
# 3. Name it: "Get Underwriter Briefing"
# 4. Copy the TOPIC DEFINITION below into the YAML editor
# 5. Click "Save"
# 6. Publish the agent
# 7. Test with: "get briefing" or "show briefing for [email@domain.com]"
#
# ============================================================================

kind: AdaptiveDialog
beginDialog:
  - kind: OnRecognizedIntent
    id: mainTrigger
    intent:
      triggerQueries:
        - get briefing
        - show briefing
        - retrieve briefing
        - get underwriter briefing
        - underwriter briefing
        - briefing report
        - show me the briefing
    actions:
      # Step 1: Ask for email
      - kind: Question
        id: emailQuestion
        prompt: "Please provide the broker email address:"
        property: Topic.brokerEmail
        inputType: Text

      # Step 2: Validate email format
      - kind: ConditionGroup
        condition: =Not(Contains(Topic.brokerEmail, "@"))
        actions:
          - kind: SendActivity
            activity: "That doesn't look like a valid email. Please try again with format: email@domain.com"
          - kind: EndDialog
            id: endInvalidEmail

      # Step 3: Call the API
      - kind: HttpRequestAction
        id: callBriefingAPI
        url: =Concatenate("https://underwriter-briefing-api.azurewebsites.net/api/GetBriefingsByEmail?email=", Topic.brokerEmail)
        method: Get
        headers:
          Content-Type: "application/json"
        response: Topic.httpResponse

      # Step 4: Check if API call succeeded
      - kind: ConditionGroup
        condition: =Topic.httpResponse.statusCode = 200
        actions:
          # Step 5: Parse and display the response
          - kind: SendActivity
            activity: =Topic.httpResponse.body

      # Step 6: Handle errors
      - kind: ConditionGroup
        condition: =Topic.httpResponse.statusCode <> 200
        actions:
          - kind: SendActivity
            activity: =Concatenate("Error (", Topic.httpResponse.statusCode, "): ", Topic.httpResponse.body)

      # Step 7: End dialog
      - kind: SendActivity
        activity: "Is there anything else you'd like to know about this briefing?"
        id: followUpQuestion

  - kind: OnUnknownIntent
    id: unknownHandler
    actions:
      - kind: SendActivity
        activity: "I can help retrieve underwriter briefings. Try saying 'get briefing' and provide a broker email address."
