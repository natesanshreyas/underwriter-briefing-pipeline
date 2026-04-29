#!/usr/bin/env python3
"""
Local API Server for Underwriter Briefing
Exposes the same endpoints as Azure Function for local testing + Copilot Studio
"""

from flask import Flask, jsonify, request
import json
import logging
from underwriter_briefing import BriefingGenerator, get_config
from azure.ai.textanalytics import TextAnalyticsClient
from azure.identity import DefaultAzureCredential

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize briefing generator
try:
    cfg = get_config()
    language_endpoint = cfg.get("LANGUAGE_ENDPOINT")

    if language_endpoint:
        client = TextAnalyticsClient(
            endpoint=language_endpoint,
            credential=DefaultAzureCredential()
        )
        generator = BriefingGenerator(client)
        logger.info("✅ Briefing generator initialized")
    else:
        generator = None
        logger.warning("⚠️ LANGUAGE_ENDPOINT not configured, using mock responses")
except Exception as e:
    generator = None
    logger.error(f"❌ Failed to initialize: {e}")


@app.route('/api/GetBriefingsByEmail', methods=['GET'])
def get_briefings_by_email():
    """
    Get all briefings for a broker email.
    
    Query params:
        email: Broker email (required)
        limit: Max results (optional, default 10)
    """
    email = request.args.get('email')
    
    if not email:
        return jsonify({"error": "Missing required parameter: 'email'"}), 400
    
    try:
        # If generator isn't available, return mock data
        if not generator:
            logger.info(f"🔍 Returning mock briefing for {email}")
            return jsonify({
                "count": 1,
                "email": email,
                "briefings": [{
                    "metadata": {
                        "broker_email": email,
                        "broker_name": "Sample Broker",
                        "broker_company": "Sample Co",
                        "email_subjects": ["Sample Email"],
                        "thread_size": 1
                    },
                    "sections": {
                        "1_executive_summary": {
                            "bullets": [
                                "[FACT] Sample briefing for testing",
                                "[FACT] Contact: Sample Broker from Sample Co",
                                "[FACT] Status: Mock data - configure Azure credentials for real analysis"
                            ]
                        },
                        "2_sentiment_and_tone": {
                            "overall_sentiment": "Neutral",
                            "confidence": 0.5,
                            "emotional_signals": [],
                            "tone_quotes": []
                        },
                        "3_key_relationships": {
                            "stakeholders": []
                        },
                        "4_broker_priorities": {
                            "explicit_goals": [],
                            "implied_goals": [],
                            "commercial_signals": []
                        },
                        "5_risk_signals": {
                            "red_flags": []
                        },
                        "6_negotiation_posture": {
                            "negotiation_style": "Unknown",
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
                            "unknowns": ["This is mock data"],
                            "follow_up_questions": []
                        },
                        "9_underwriter_prep": {
                            "talking_points": [],
                            "questions_to_ask": [],
                            "lean_in_areas": [],
                            "proceed_cautiously": [],
                            "opening_statement": ""
                        },
                        "10_confidence_and_limitations": {
                            "overall_confidence": 0.0,
                            "confidence_scale": "0=No confidence, 1=Full confidence",
                            "limitations": ["Mock data - not real analysis"]
                        }
                    }
                }]
            }), 200
        
        # Real briefing generation
        sample_email = """
        Hi Jordan,
        
        Wanted to let you know we've completed our initial review of the renewal. 
        The submission was well organized, and the additional context you provided was helpful. 
        We're aligned on next steps and expect to have an updated indication ready shortly. 
        I'll make sure you have everything you need to keep the process moving smoothly with your client.
        
        Thanks again for the collaboration—looking forward to closing this one together.
        
        Best,
        Broker Contact
        """
        
        briefing = generator.generate_briefing(
            broker_email=email,
            body_text=sample_email,
            subject="Renewal Discussion",
            sender_name="Broker Contact",
            sender_company="Broker Company"
        )
        
        logger.info(f"✅ Generated briefing for {email}")
        return jsonify({
            "count": 1,
            "email": email,
            "briefings": [briefing.to_dict()]
        }), 200
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "Underwriter Briefing API",
        "generator": "ready" if generator else "mock-only"
    }), 200


@app.route('/', methods=['GET'])
def index():
    """Root endpoint with API documentation"""
    return jsonify({
        "service": "Underwriter Briefing API (Local)",
        "version": "1.0",
        "endpoints": {
            "GET /api/GetBriefingsByEmail": {
                "description": "Get briefing for a broker email",
                "params": {
                    "email": "Broker email address (required)",
                    "limit": "Max results (optional, default 10)"
                },
                "example": "/api/GetBriefingsByEmail?email=broker@company.com"
            },
            "GET /health": {
                "description": "Health check",
                "example": "/health"
            }
        }
    }), 200


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 UNDERWRITER BRIEFING API - LOCAL SERVER")
    print("="*60)
    print("\n✅ Starting on http://127.0.0.1:5000")
    print("✅ Test endpoint: http://127.0.0.1:5000/api/GetBriefingsByEmail?email=test@example.com")
    print("✅ Health check: http://127.0.0.1:5000/health")
    print("\n" + "="*60 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
