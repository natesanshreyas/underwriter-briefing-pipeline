#!/usr/bin/env python3
"""
Test Briefing API Response - For local testing before deploying to Azure

Generates sample JSON response that Copilot Studio expects.
Use this to test the topic definition locally.
"""

import json
from underwriter_briefing import BriefingGenerator, format_briefing_as_markdown
from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential
from underwriter_briefing import get_config

def test_briefing_api_response():
    """Generate a sample briefing and output as JSON."""
    
    cfg = get_config()
    language_endpoint = cfg.get("LANGUAGE_ENDPOINT")
    language_key = cfg.get("LANGUAGE_KEY")
    
    if not language_endpoint or not language_key:
        print(json.dumps({
            "count": 0,
            "briefings": [
                {
                    "metadata": {
                        "broker_email": "shreyas@acme.com",
                        "broker_name": "Shreyas",
                        "broker_company": "Acme Manufacturing",
                        "email_subjects": ["Email 2 – Positive / Proactive"],
                        "thread_size": 1,
                    },
                    "sections": {
                        "1_executive_summary": {
                            "bullets": [
                                "[FACT] Purpose: Email 2 – Positive / Proactive",
                                "[INFERRED] Broker Stance: Positive tone with Supportive, Collaborative signals (conf: 92%)",
                                "[FACT] Key Contact: Shreyas from Acme Manufacturing",
                                "[FACT] Sentiment Confidence: 92% (based on email tone analysis)",
                                "[FACT] Status: Requires underwriting review and follow-up"
                            ]
                        },
                        "2_sentiment_and_tone": {
                            "overall_sentiment": "Positive",
                            "confidence": 0.92,
                            "emotional_signals": ["Supportive", "Collaborative"],
                            "tone_quotes": [
                                {"quote": "Overall email demonstrates positive sentiment", "location": "Full email analysis"}
                            ]
                        },
                        "3_key_relationships": {
                            "stakeholders": [
                                {
                                    "name": "[FACT] Shreyas",
                                    "role": "Primary Broker Contact",
                                    "influence_level": "High",
                                    "relationship_signal": "Advocate",
                                    "notes": "Sent from Acme Manufacturing"
                                }
                            ]
                        },
                        "4_broker_priorities": {
                            "explicit_goals": [
                                {
                                    "text": "[FACT] aligned on next steps",
                                    "category": "priority",
                                    "source": "explicit",
                                    "confidence": 0.95,
                                    "citation": None,
                                    "reasoning": None
                                }
                            ],
                            "implied_goals": [
                                {
                                    "text": "[INFERRED] Build collaborative relationship",
                                    "category": "relationship_goal",
                                    "source": "inferred",
                                    "confidence": 0.80,
                                    "citation": None,
                                    "reasoning": "Positive sentiment + collaborative language suggests relationship-focused engagement"
                                }
                            ],
                            "commercial_signals": [
                                "Direct outreach from Acme Manufacturing",
                                "Primary contact: Shreyas",
                                "Engagement channel: Email"
                            ]
                        },
                        "5_risk_signals": {
                            "red_flags": []
                        },
                        "6_negotiation_posture": {
                            "negotiation_style": "Collaborative",
                            "pressure_tactics": [],
                            "past_objections": []
                        },
                        "7_key_facts_snapshot": {
                            "insured_name": None,
                            "line_of_business": [],
                            "renewal_date": None,
                            "premium": None,
                            "limits": [],
                            "loss_history": None,
                            "special_conditions": []
                        },
                        "8_missing_information": {
                            "unknowns": [
                                "Specific line(s) of business not clearly stated",
                                "Coverage limits and deductibles not specified",
                                "Loss history/claims experience not provided",
                                "Current premium and terms not mentioned"
                            ],
                            "follow_up_questions": [
                                "What are the insured's primary coverage requirements?",
                                "What is the current renewal date and policy term?"
                            ]
                        },
                        "9_underwriter_prep": {
                            "talking_points": [
                                "Emphasize partnership approach",
                                "Highlight mutual benefits",
                                "Show understanding of their priorities"
                            ],
                            "questions_to_ask": [],
                            "lean_in_areas": [
                                "Collaborative relationship building",
                                "Quick response and engagement"
                            ],
                            "proceed_cautiously": [],
                            "opening_statement": "Thank you for reaching out, Shreyas. We appreciate the opportunity..."
                        },
                        "10_confidence_and_limitations": {
                            "overall_confidence": 0.89,
                            "confidence_scale": "0=No confidence, 1=Full confidence",
                            "limitations": [
                                "Single email analyzed; full thread provides more context",
                                "Generic NER and sentiment models used"
                            ]
                        }
                    }
                }
            ]
        }, indent=2))
        return
    
    # Create client and generate real briefing
    client = TextAnalyticsClient(
        endpoint=language_endpoint,
        credential=AzureKeyCredential(language_key)
    )
    
    sample_email = """
    Hi Jordan,
    
    Wanted to let you know we've completed our initial review of the Acme Manufacturing renewal. 
    The submission was well organized, and the additional context you provided was helpful. 
    We're aligned on next steps and expect to have an updated indication ready shortly. 
    I'll make sure you have everything you need to keep the process moving smoothly with your client.
    
    Thanks again for the collaboration—looking forward to closing this one together.
    
    Best,
    Shreyas
    """
    
    generator = BriefingGenerator(client)
    briefing = generator.generate_briefing(
        broker_email="shreyas@acme.com",
        body_text=sample_email,
        subject="Email 2 – Positive / Proactive",
        sender_name="Shreyas",
        sender_company="Acme Manufacturing"
    )
    
    # Output as JSON (what Copilot Studio expects)
    response = {
        "count": 1,
        "briefings": [briefing.to_dict()]
    }
    
    print(json.dumps(response, indent=2, default=str))


if __name__ == "__main__":
    test_briefing_api_response()
