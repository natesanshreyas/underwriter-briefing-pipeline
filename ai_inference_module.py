"""
AI-Driven Inference Module

Replaces hardcoded rules with GPT-4 powered inference generation.
Produces real inferences grounded in actual email quotes with confidence scoring.
"""

import json
from openai import AzureOpenAI
from typing import Optional, Dict, List, Tuple
from underwriter_briefing import ExtractedFact, SourceType

def generate_ai_inferences(
    body_text: str,
    sender_name: str,
    sender_company: str,
    subject: str,
    sentiment: str,
    sentiment_confidence: float,
    openai_client: AzureOpenAI,
    model: str = "gpt-4o-mini"
) -> Dict[str, List[ExtractedFact]]:
    """
    Use GPT-4 to generate AI-driven inferences from email text.
    
    Returns:
    {
        "implied_goals": [ExtractedFact, ...],
        "risk_inferences": [ExtractedFact, ...],
        "confidence_notes": [str, ...]
    }
    """
    
    prompt = f"""
Analyze this broker email and generate INTELLIGENT INFERENCES (not rules).

EMAIL:
From: {sender_name} ({sender_company})
Subject: {subject}
Sentiment: {sentiment} ({sentiment_confidence:.0%})

Body:
{body_text}

---

Generate inferences in the following JSON format. Be SPECIFIC and QUOTE-based:

{{
    "implied_goals": [
        {{
            "text": "What the broker likely wants (inferred)",
            "reasoning": "Why you think this - be specific about what in the email suggests this",
            "supporting_quote": "Direct quote from email that supports this",
            "confidence": 0.0-0.95,
            "category": "relationship_goal|conflict_resolution|opportunity|risk_mitigation|other"
        }}
    ],
    "risk_inferences": [
        {{
            "text": "Potential risk or concern not explicitly stated",
            "reasoning": "Why this might be a concern",
            "supporting_quote": "Quote that hints at this",
            "confidence": 0.0-0.95,
            "category": "hidden_pressure|unstated_concern|timing_issue|relationship_tension|other"
        }}
    ],
    "confidence_limitations": [
        "Limitation 1",
        "Limitation 2"
    ]
}}

Instructions:
1. Inferences must be grounded in actual quotes
2. Confidence scores should be 0.0-0.95 (capped at 95% for inferred)
3. Generate 2-4 implied goals and 1-3 risk inferences
4. Be specific - not generic
5. Quote supporting evidence directly from the email
6. Return ONLY valid JSON
"""
    
    try:
        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert underwriting analyst. Generate specific, quote-based inferences."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            top_p=0.95
        )
        
        response_text = response.choices[0].message.content
        
        # Parse JSON response
        data = json.loads(response_text)
        
        # Convert to ExtractedFact objects
        implied_goals = [
            ExtractedFact(
                text=goal["text"],
                category=goal.get("category", "inferred_goal"),
                source=SourceType.INFERRED,
                confidence=min(goal["confidence"], 0.95),  # Cap at 95%
                reasoning=goal["reasoning"],
            )
            for goal in data.get("implied_goals", [])
        ]
        
        risk_inferences = [
            ExtractedFact(
                text=risk["text"],
                category=risk.get("category", "inferred_risk"),
                source=SourceType.INFERRED,
                confidence=min(risk["confidence"], 0.95),
                reasoning=risk["reasoning"],
            )
            for risk in data.get("risk_inferences", [])
        ]
        
        return {
            "implied_goals": implied_goals,
            "risk_inferences": risk_inferences,
            "confidence_limitations": data.get("confidence_limitations", [])
        }
    
    except Exception as e:
        print(f"⚠️  AI inference generation failed: {str(e)}")
        # Fallback to empty if AI fails
        return {
            "implied_goals": [],
            "risk_inferences": [],
            "confidence_limitations": [f"AI inference failed: {str(e)}"]
        }


def generate_ai_confidence_section(
    briefing_data: Dict,
    openai_client: AzureOpenAI,
    model: str = "gpt-4o-mini"
) -> Tuple[float, List[str]]:
    """
    Use GPT-4 to generate contextual confidence & limitations section.
    Instead of hardcoded text, analyzes what's ACTUALLY missing from the briefing.
    
    Returns:
        (overall_confidence, limitations_list)
    """
    
    # Analyze what's in the briefing
    sections = briefing_data.get("sections", {})
    
    analysis_prompt = f"""
Analyze this underwriter briefing and generate SPECIFIC, CONTEXTUAL limitations.

BRIEFING DATA:
- Sentiment: {sections.get('2_sentiment_and_tone', {}).get('overall_sentiment', 'Unknown')}
- Stakeholders: {len(sections.get('3_key_relationships', {}).get('stakeholders', []))} identified
- Explicit Goals: {len(sections.get('4_broker_priorities', {}).get('explicit_goals', []))} found
- Risk Signals: {len(sections.get('5_risk_signals', {}).get('red_flags', []))} found
- Missing Info Items: {len(sections.get('8_missing_information', {}).get('unknowns', []))} identified
- Insured Name: {sections.get('7_key_facts_snapshot', {}).get('insured_name') or 'NOT PROVIDED'}
- Premium: {sections.get('7_key_facts_snapshot', {}).get('premium') or 'NOT PROVIDED'}

Generate JSON with:
{{
    "confidence_score": 0.0-1.0,
    "confidence_reasoning": "Why this confidence level",
    "limitations": [
        "Specific limitation based on missing data",
        "Specific limitation based on analysis",
        ...
    ]
}}

Be SPECIFIC to THIS briefing, not generic. Reference what's actually missing.
Return ONLY valid JSON.
"""
    
    try:
        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert underwriting QA analyst. Generate specific, contextual confidence assessments."},
                {"role": "user", "content": analysis_prompt}
            ],
            temperature=0.7
        )
        
        response_text = response.choices[0].message.content
        data = json.loads(response_text)
        
        return (
            data.get("confidence_score", 0.75),
            data.get("limitations", [])
        )
    
    except Exception as e:
        print(f"⚠️  AI confidence generation failed: {str(e)}")
        return (0.75, [f"AI analysis unavailable: {str(e)}"])


if __name__ == "__main__":
    # Example usage
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    import os

    _credential = DefaultAzureCredential()
    client = AzureOpenAI(
        azure_ad_token_provider=get_bearer_token_provider(
            _credential, "https://cognitiveservices.azure.com/.default"
        ),
        api_version="2024-02-15-preview",
        azure_endpoint=os.getenv("OPENAI_ENDPOINT")
    )
    
    sample_email = """Hi Jordan,
    
Wanted to let you know we've completed our initial review of the Acme Manufacturing renewal. 
The submission was well organized, and the additional context you provided was helpful. 
We're aligned on next steps and expect to have an updated indication ready shortly. 
I'll make sure you have everything you need to keep the process moving smoothly with your client.

One thing worth noting: there's some competitive pressure on this one, so timing is important. 
We'd like to get binding authority confirmed by Friday if possible.

Thanks again for the collaboration—looking forward to closing this one together.

Best,
Shreyas"""

    inferences = generate_ai_inferences(
        sample_email,
        "Shreyas",
        "Acme Manufacturing",
        "Renewal Discussion",
        "Positive",
        0.74,
        client
    )
    
    print("Generated Inferences:")
    print(json.dumps(inferences, indent=2, default=str))
