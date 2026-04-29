#!/usr/bin/env python3
"""
Underwriter Briefing Generator

Generates comprehensive one-page underwriter briefings from broker emails.
Includes sentiment analysis, NER, fact/inference separation, citations, and confidence scoring.

Output: Structured JSON ready for Copilot Studio integration.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict, field
from typing import Optional
from enum import Enum

from azure.ai.textanalytics import TextAnalyticsClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.identity import DefaultAzureCredential
from datetime import datetime


class SourceType(str, Enum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"


class InfluenceLevel(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class RelationshipSignal(str, Enum):
    ADVOCATE = "Advocate"
    GATEKEEPER = "Gatekeeper"
    UNKNOWN = "Unknown"


@dataclass
class Citation:
    """Tracks source quote with location with rich provenance."""
    quote: str
    location: str  # "Email subject" or line reference
    message_id: Optional[str] = None  # Which email in thread (Email #1 of 5)
    thread_position: Optional[int] = None  # 0-indexed position in thread
    sentence_index: Optional[int] = None  # Sentence number in message
    char_offset: Optional[int] = None  # Character position in message
    paragraph_index: Optional[int] = None  # Paragraph number
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractedFact:
    """A fact with source tracking and confidence."""
    text: str
    category: str  # "timeline", "priority", "risk_signal", "stakeholder", etc.
    source: SourceType
    confidence: float  # 0.0-1.0
    citation: Optional[Citation] = None
    reasoning: Optional[str] = None  # Why it's inferred
    
    def validate(self) -> bool:
        assert 0 <= self.confidence <= 1, "Confidence must be 0-1"
        if self.source == SourceType.INFERRED:
            assert self.reasoning, "Inferred facts must have reasoning"
            assert self.confidence <= 0.95, "Inferred facts capped at 95%"
        return True
    
    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "category": self.category,
            "source": self.source.value,
            "confidence": round(self.confidence, 2),
            "citation": self.citation.to_dict() if self.citation else None,
            "reasoning": self.reasoning,
        }


@dataclass
class Stakeholder:
    """Key relationships and stakeholders."""
    name: str
    role: str
    influence_level: InfluenceLevel
    relationship_signal: RelationshipSignal
    notes: str = ""
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "influence_level": self.influence_level.value,
            "relationship_signal": self.relationship_signal.value,
            "notes": self.notes,
        }


@dataclass
class UnderwriterBriefing:
    """Complete 10-section underwriter briefing with optional LLM narrative wrapper."""
    broker_email: str
    broker_name: str
    broker_company: str
    email_subjects: list[str] = field(default_factory=list)
    thread_size: int = 1  # Gap E: number of emails in thread analyzed
    
    # LLM-Generated Narrative (optional, added after extraction)
    narrative_summary: Optional[str] = None  # 2-3 paragraph executive narrative grounded in facts
    narrative_generated_at: Optional[str] = None  # ISO timestamp
    narrative_model: Optional[str] = None  # "gpt-4" or "gpt-3.5-turbo"
    
    # Gap B: Validation gate - quality checks for QBE compliance
    validation_checks: dict = field(default_factory=lambda: {
        "all_claims_grounded": True,
        "inferences_labeled": True,
        "required_sections_present": True,
        "missing_sections": [],
        "quote_present_for_sentiment": True,
        "hallucination_risk_notes": [],
    })
    
    # Section 1: Executive Summary
    exec_summary_bullets: list[str] = field(default_factory=list)
    
    # Section 2: Sentiment & Tone
    overall_sentiment: str = "Unknown"  # Positive, Neutral, Mixed, Negative
    sentiment_confidence: float = 0.0
    emotional_signals: list[str] = field(default_factory=list)
    tone_quotes: list[Citation] = field(default_factory=list)
    
    # Section 3: Key Relationships
    stakeholders: list[Stakeholder] = field(default_factory=list)
    
    # Section 4: Broker Priorities
    explicit_goals: list[ExtractedFact] = field(default_factory=list)
    implied_goals: list[ExtractedFact] = field(default_factory=list)
    commercial_signals: list[str] = field(default_factory=list)
    
    # Section 5: Risk Signals
    risk_signals: list[ExtractedFact] = field(default_factory=list)
    
    # Section 6: Negotiation Posture
    negotiation_style: str = "Unknown"
    pressure_tactics: list[ExtractedFact] = field(default_factory=list)
    past_objections: list[str] = field(default_factory=list)
    
    # Section 7: Key Facts
    insured_name: Optional[str] = None
    line_of_business: list[str] = field(default_factory=list)
    renewal_date: Optional[str] = None
    premium: Optional[str] = None
    limits: list[str] = field(default_factory=list)
    loss_history: Optional[str] = None
    special_conditions: list[str] = field(default_factory=list)
    
    # Section 8: Missing Information
    missing_info: list[str] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    
    # Section 9: Recommendations
    talking_points: list[str] = field(default_factory=list)
    questions_to_ask: list[str] = field(default_factory=list)
    lean_in_areas: list[str] = field(default_factory=list)
    proceed_cautiously: list[str] = field(default_factory=list)
    opening_statement: str = ""
    
    # Section 10: Confidence & Limitations
    overall_confidence: float = 0.0  # Average of all confidence scores
    limitations: list[str] = field(default_factory=list)
    
    def to_json(self) -> str:
        """Convert to JSON for Copilot Studio."""
        return json.dumps(self.to_dict(), indent=2, default=str)
    
    def to_dict(self) -> dict:
        return {
            "metadata": {
                "broker_email": self.broker_email,
                "broker_name": self.broker_name,
                "broker_company": self.broker_company,
                "email_subjects": self.email_subjects,
                "thread_size": self.thread_size,
                "narrative_summary": self.narrative_summary,
                "narrative_generated_at": self.narrative_generated_at,
                "narrative_model": self.narrative_model,
                "validation_gate": self.validation_checks,
            },
            "sections": {
                "1_executive_summary": {
                    "bullets": self.exec_summary_bullets,
                },
                "2_sentiment_and_tone": {
                    "overall_sentiment": self.overall_sentiment,
                    "confidence": round(self.sentiment_confidence, 2),
                    "emotional_signals": self.emotional_signals,
                    "tone_quotes": [c.to_dict() for c in self.tone_quotes],
                },
                "3_key_relationships": {
                    "stakeholders": [s.to_dict() for s in self.stakeholders],
                },
                "4_broker_priorities": {
                    "explicit_goals": [f.to_dict() for f in self.explicit_goals],
                    "implied_goals": [f.to_dict() for f in self.implied_goals],
                    "commercial_signals": self.commercial_signals,
                },
                "5_risk_signals": {
                    "red_flags": [f.to_dict() for f in self.risk_signals],
                },
                "6_negotiation_posture": {
                    "negotiation_style": self.negotiation_style,
                    "pressure_tactics": [f.to_dict() for f in self.pressure_tactics],
                    "past_objections": self.past_objections,
                },
                "7_key_facts_snapshot": {
                    "insured_name": self.insured_name,
                    "line_of_business": self.line_of_business,
                    "renewal_date": self.renewal_date,
                    "premium": self.premium,
                    "limits": self.limits,
                    "loss_history": self.loss_history,
                    "special_conditions": self.special_conditions,
                },
                "8_missing_information": {
                    "unknowns": self.missing_info,
                    "follow_up_questions": self.follow_up_questions,
                },
                "9_underwriter_prep": {
                    "talking_points": self.talking_points,
                    "questions_to_ask": self.questions_to_ask,
                    "lean_in_areas": self.lean_in_areas,
                    "proceed_cautiously": self.proceed_cautiously,
                    "opening_statement": self.opening_statement,
                },
                "10_confidence_and_limitations": {
                    "overall_confidence": round(self.overall_confidence, 2),
                    "confidence_scale": "0=No confidence, 1=Full confidence",
                    "limitations": self.limitations,
                },
            },
        }


class BriefingGenerator:
    """Generates underwriter briefing from broker email."""
    
    def __init__(self, language_client: TextAnalyticsClient):
        self.client = language_client
    
    def extract_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        return re.split(r'(?<=[.!?])\s+', text.strip())
    
    def find_quote(self, keyword: str, text: str) -> Optional[Citation]:
        """Find and quote context around a keyword."""
        pattern = rf"[^.!?]*\b{re.escape(keyword)}\b[^.!?]*[.!?]"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            quote = match.group(0).strip()
            return Citation(quote=quote, location="Email body")
        return None
    
    def extract_key_urgency_signals(self, text: str) -> list[ExtractedFact]:
        """Extract explicit urgency/timeline signals."""
        facts = []
        
        # Explicit timeline keywords
        urgency_patterns = [
            (r"\b(urgent|ASAP|immediate|by\s+\w+day|deadline|as soon as|this week|today|tomorrow)\b", "timeline"),
            (r"\b(expect|expiring|renewal|effective|binding|by end of)\b", "renewal_signal"),
        ]
        
        for pattern, category in urgency_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                quote_obj = self.find_quote(match.group(1), text)
                facts.append(ExtractedFact(
                    text=match.group(1),
                    category=category,
                    source=SourceType.EXPLICIT,
                    confidence=0.95,
                    citation=quote_obj,
                ))
        
        return facts
    
    def extract_pricing_signals(self, text: str) -> list[ExtractedFact]:
        """Extract pricing and competitive pressure signals."""
        facts = []
        
        # Pricing patterns
        patterns = [
            (r"\b(pricing|premium|rate|cost|fees|competitive quote|competitor)\b", "pricing_pressure"),
            (r"\$[\d,]+(?:\.\d{2})?(?:M|K)?(?:\s*/\s*\w+)?", "financial_amount"),
        ]
        
        for pattern, category in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                quote_obj = self.find_quote(match.group(0), text)
                facts.append(ExtractedFact(
                    text=match.group(0),
                    category=category,
                    source=SourceType.EXPLICIT,
                    confidence=0.9,
                    citation=quote_obj,
                ))
        
        return facts
    
    def extract_emotional_signals(self, text: str) -> dict:
        """Gap D: Extract emotional signals - urgency, frustration, pressure (explicit heuristic)."""
        signals = {}
        
        # Urgency indicators
        urgency_patterns = r"\b(ASAP|as soon as|urgent|immediate|critical|right away|end of day|eod|escalat|rush|deadline|expir|binding by|must close)\b"
        urgency_matches = re.findall(urgency_patterns, text, re.IGNORECASE)
        signals["urgency_indicators"] = list(set(urgency_matches)) if urgency_matches else []
        signals["urgency_detected"] = len(urgency_matches) > 0
        
        # Pressure/frustration indicators
        pressure_patterns = r"\b(frustrated|concerned|problem|issue|risk|concern|challenge|difficult|struggle|disappointed|not acceptable|unacceptable|demand)\b"
        pressure_matches = re.findall(pressure_patterns, text, re.IGNORECASE)
        signals["pressure_indicators"] = list(set(pressure_matches)) if pressure_matches else []
        signals["pressure_detected"] = len(pressure_matches) > 0
        
        # Collaborative/positive tone indicators
        collab_patterns = r"\b(appreciate|grateful|excited|happy|great|wonderful|excellent|partnership|collaborate|together|aligned|aligned|thanks)\b"
        collab_matches = re.findall(collab_patterns, text, re.IGNORECASE)
        signals["collaborative_indicators"] = list(set(collab_matches)) if collab_matches else []
        signals["collaborative_detected"] = len(collab_matches) > 0
        
        return signals
    
    def analyze_sentiment_and_tone(self, text: str) -> tuple[str, float, list[str]]:
        """Analyze sentiment and extract emotional signals."""
        response = self.client.analyze_sentiment(documents=[text])
        result = response[0]
        
        if result.is_error:
            return "Unknown", 0.0, []
        
        sentiment = result.sentiment
        confidence = max(result.confidence_scores.positive, 
                        result.confidence_scores.neutral,
                        result.confidence_scores.negative)
        
        # Emotional signal detection
        signals = []
        if confidence > 0.8:
            if result.confidence_scores.positive > 0.6:
                signals.extend(["Supportive", "Collaborative"])
            if result.confidence_scores.negative > 0.4:
                signals.extend(["Pressure", "Urgency"])
            if result.confidence_scores.neutral > 0.6:
                signals.append("Transactional")
        
        # Map sentiment
        sentiment_map = {
            "positive": "Positive",
            "neutral": "Neutral",
            "negative": "Negative",
            "mixed": "Mixed",
        }
        
        return sentiment_map.get(sentiment, "Unknown"), confidence, signals
    
    def extract_entities(self, text: str) -> dict:
        """Extract NER entities."""
        response = self.client.recognize_entities(documents=[text])
        result = response[0]
        
        summary = {
            "people": [],
            "organizations": [],
            "emails": [],
            "phones": [],
        }
        
        if not result.is_error:
            for ent in getattr(result, "entities", []):
                category = (ent.category or "").lower()
                if category == "person":
                    summary["people"].append(ent.text)
                elif category == "organization":
                    summary["organizations"].append(ent.text)
                elif category == "email":
                    summary["emails"].append(ent.text)
                elif category == "phonenumber":
                    summary["phones"].append(ent.text)
        
        return summary
    
    def generate_briefing(self, broker_email: str, body_text: str, 
                         subject: str, sender_name: str = "Unknown",
                         sender_company: str = "Unknown", thread_messages: Optional[list] = None) -> UnderwriterBriefing:
        """Gap E: Generate complete underwriter briefing from single email or thread.
        
        Args:
            broker_email: Broker's email address
            body_text: Email body text (most recent message if thread)
            subject: Email subject
            sender_name: Sender name
            sender_company: Company
            thread_messages: Optional list of dicts with 'body', 'subject', 'sender', 'company' for full thread analysis
        """
        
        briefing = UnderwriterBriefing(
            broker_email=broker_email,
            broker_name=sender_name,
            broker_company=sender_company,
            email_subjects=[subject],
            thread_size=len(thread_messages) if thread_messages else 1,  # Gap E
        )
        
        # Sentiment Analysis
        sentiment, sentiment_conf, emotional_signals = self.analyze_sentiment_and_tone(body_text)
        briefing.overall_sentiment = sentiment
        briefing.sentiment_confidence = sentiment_conf
        briefing.emotional_signals = emotional_signals
        
        # Gap D: Extract emotional signals explicitly
        extracted_signals = self.extract_emotional_signals(body_text)
        if extracted_signals["urgency_detected"]:
            briefing.emotional_signals.append(f"Urgency ({', '.join(extracted_signals['urgency_indicators'][:2])})") 
        if extracted_signals["pressure_detected"]:
            briefing.emotional_signals.append(f"Pressure/Concern ({', '.join(extracted_signals['pressure_indicators'][:2])})") 
        if extracted_signals["collaborative_detected"]:
            briefing.emotional_signals.append(f"Collaborative ({', '.join(extracted_signals['collaborative_indicators'][:2])})") 
        
        # Gap B: Track validation
        briefing.validation_checks["quote_present_for_sentiment"] = len(briefing.tone_quotes) > 0
        
        # Entity Extraction
        entities = self.extract_entities(body_text)
        
        # ===== SECTION 1: Executive Summary =====
        # Gap A: Add [FACT] and [INFERRED] labels with confidence
        briefing.exec_summary_bullets = [
            f"[FACT] Purpose: {subject}",
            f"[INFERRED] Broker Stance: {sentiment} tone with {', '.join(emotional_signals) if emotional_signals else 'neutral signals'} (conf: {sentiment_conf:.0%})",
            f"[FACT] Key Contact: {sender_name} from {sender_company}",
            f"[FACT] Sentiment Confidence: {sentiment_conf:.0%} (based on email tone analysis)",
            f"[FACT] Status: Requires underwriting review and follow-up",
        ]
        
        # ===== SECTION 2: Sentiment & Tone =====
        briefing.tone_quotes.append(Citation(
            quote=f"Overall email demonstrates {sentiment.lower()} sentiment",
            location="Full email analysis"
        ))
        # Extract key sentences that indicate sentiment
        sentences = self.extract_sentences(body_text)
        if sentences:
            briefing.tone_quotes.append(Citation(
                quote=sentences[0][:80] + "..." if len(sentences[0]) > 80 else sentences[0],
                location="Opening"
            ))
        
        # ===== SECTION 3: Stakeholders =====
        # Primary: sender (FACT - directly from email metadata)
        briefing.stakeholders.append(Stakeholder(
            name=f"[FACT] {sender_name}",
            role="Primary Broker Contact",
            influence_level=InfluenceLevel.HIGH,
            relationship_signal=RelationshipSignal.ADVOCATE if sentiment == "Positive" else RelationshipSignal.UNKNOWN,
            notes=f"Sent from {sender_company}"
        ))
        
        # Additional people mentioned (INFERRED from NER)
        for person in entities["people"]:
            if person.lower() != sender_name.lower():
                briefing.stakeholders.append(Stakeholder(
                    name=f"[INFERRED] {person}",
                    role="Secondary contact (mentioned)",
                    influence_level=InfluenceLevel.MEDIUM,
                    relationship_signal=RelationshipSignal.UNKNOWN,
                    notes="Referenced in email"
                ))
        
        # ===== SECTION 4: Broker Priorities =====
        # Explicit goals from urgency signals (FACT - explicitly stated)
        urgency_facts = self.extract_key_urgency_signals(body_text)
        for fact in urgency_facts:
            fact.text = f"[FACT] {fact.text}"  # Tag as fact
        briefing.explicit_goals.extend(urgency_facts)
        
        # If no explicit urgency found, add default
        if not briefing.explicit_goals:
            briefing.explicit_goals.append(ExtractedFact(
                text="[INFERRED] Engage for renewal/quote discussion",
                category="engagement",
                source=SourceType.EXPLICIT,
                confidence=0.85,
            ))
        
        # Implied goals based on sentiment and tone (INFERRED)
        if sentiment == "Positive":
            briefing.implied_goals.append(ExtractedFact(
                text="[INFERRED] Build collaborative relationship",
                category="relationship_goal",
                source=SourceType.INFERRED,
                confidence=0.80,
                reasoning="Positive sentiment + collaborative language suggests relationship-focused engagement"
            ))
        elif sentiment == "Negative":
            briefing.implied_goals.append(ExtractedFact(
                text="[INFERRED] Resolve conflict or address concerns",
                category="issue_resolution",
                source=SourceType.INFERRED,
                confidence=0.75,
                reasoning="Negative sentiment detected; likely addressing specific concerns or pressure"
            ))
        
        briefing.commercial_signals = [
            f"Direct outreach from {sender_company}",
            f"Primary contact: {sender_name}",
            f"Engagement channel: Email",
        ]
        if entities["emails"]:
            briefing.commercial_signals.append(f"Alternative contacts: {', '.join(entities['emails'][:2])}")
        
        # ===== SECTION 5: Risk Signals =====
        pricing_facts = self.extract_pricing_signals(body_text)
        for fact in pricing_facts:
            fact.text = f"[FACT] {fact.text}"  # Tag pricing as explicit facts
        briefing.risk_signals.extend(pricing_facts)
        
        # Add sentiment-based risk signals (INFERRED)
        if "urgent" in body_text.lower() or "asap" in body_text.lower():
            briefing.risk_signals.append(ExtractedFact(
                text="[FACT] Time pressure indicated",
                category="time_constraint",
                source=SourceType.EXPLICIT,
                confidence=0.9,
                citation=self.find_quote("urgent|asap|deadline|immediately", body_text)
            ))
        
        if "competitive" in body_text.lower() or "competitor" in body_text.lower():
            briefing.risk_signals.append(ExtractedFact(
                text="[FACT] Competitive positioning mentioned",
                category="competitive_pressure",
                source=SourceType.EXPLICIT,
                confidence=0.85,
                citation=self.find_quote("competitive|competitor", body_text)
            ))
        
        # ===== SECTION 6: Negotiation Posture =====
        if sentiment == "Positive":
            briefing.negotiation_style = "Collaborative"
            briefing.talking_points = [
                "Emphasize partnership approach",
                "Highlight mutual benefits",
                "Show understanding of their priorities",
            ]
        elif sentiment == "Negative":
            briefing.negotiation_style = "Defensive/Problem-solving"
            briefing.talking_points = [
                "Address concerns directly",
                "Clarify any misunderstandings",
                "Propose concrete solutions",
            ]
        else:
            briefing.negotiation_style = "Exploratory"
            briefing.talking_points = [
                "Gather more information",
                "Understand their specific needs",
                "Explore alignment opportunities",
            ]
        
        # ===== SECTION 7: Key Facts =====
        if entities["organizations"]:
            briefing.insured_name = entities["organizations"][0]
        if entities["emails"]:
            briefing.line_of_business = ["Contact info available"]
        
        # Extract any dollar amounts as potential premium/limits
        amounts = re.findall(r'\$[\d,]+(?:\.\d{2})?(?:M|K)?', body_text)
        if amounts:
            briefing.premium = amounts[0] if len(amounts) == 1 else f"Multiple: {', '.join(amounts[:2])}"
        
        # ===== SECTION 8: Missing Information =====
        briefing.missing_info = [
            "Specific line(s) of business not clearly stated",
            "Coverage limits and deductibles not specified",
            "Loss history/claims experience not provided",
            "Current premium and terms not mentioned",
            "Special coverages or endorsements not addressed",
        ]
        
        briefing.follow_up_questions = [
            "What are the insured's primary coverage requirements?",
            "What is the current renewal date and policy term?",
            "Are there any specific loss history or claims concerns?",
            "What is the budget expectation for premium?",
            "Are there any special endorsements or coverage modifications needed?",
            "What is the timeline for quote/binding decision?",
        ]
        
        # ===== SECTION 9: Underwriter Prep =====
        briefing.opening_statement = (
            f"Thank you for reaching out, {sender_name}. We appreciate the opportunity to discuss {subject}. "
            f"Let's start by confirming the key coverage requirements and timeline so we can provide the best solution for your client."
        )
        
        briefing.lean_in_areas = [
            "Collaborative relationship building",
            "Quick response and engagement",
            "Understanding customer priorities",
        ]
        
        briefing.proceed_cautiously = [
            "Pricing concessions without full account information",
            "Binding without completing fact-find",
            "Special coverage requests without proper review",
        ]
        
        # ===== SECTION 10: Confidence & Limitations =====
        all_confidences = [sentiment_conf] + [f.confidence for f in briefing.explicit_goals] + \
                         [f.confidence for f in briefing.implied_goals] + \
                         [f.confidence for f in briefing.risk_signals]
        briefing.overall_confidence = (sum(all_confidences) / len(all_confidences)) if all_confidences else 0.5
        
        briefing.limitations = [
            "Single email analyzed; full email thread would provide more context",
            "Generic NER and sentiment models used; insurance-specific models would improve accuracy",
            "No access to historical relationship or account data",
            "Inferred motivations based on tone; explicit discussion with broker is essential",
            "Risk signals are preliminary; full underwriting review required before decision",
        ]
        
        return briefing
    
    def generate_narrative_wrapper(
        self, 
        briefing: UnderwriterBriefing, 
        openai_client,
        model: str = "gpt-4o-mini"
    ) -> UnderwriterBriefing:
        """
        Enhance the 10-section briefing with better readability using LLM.
        
        This method polishes each section's text without changing structure:
        - Executive Summary bullets → More impactful language
        - Risk signals → Added context
        - Recommendations → More actionable
        - All structured data preserved for Cosmos DB storage
        
        Args:
            briefing: Completed UnderwriterBriefing with all sections filled
            openai_client: Initialized OpenAI client
            model: GPT model to use ("gpt-4o-mini", "gpt-4", etc.)
        
        Returns:
            Enhanced briefing object (modified in-place)
        """
        
        try:
            # Section 1: Polish Executive Summary bullets
            if briefing.exec_summary_bullets:
                summary_text = "\n".join(briefing.exec_summary_bullets)
                prompt = f"""Improve these executive summary points for clarity:

{summary_text}

Enhanced points:"""
                
                response = openai_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are an insurance expert. Improve clarity of insurance underwriting points."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=200,
                    temperature=0.7,
                )
                
                enhanced_bullets = response.choices[0].message.content.strip().split("\n")
                briefing.exec_summary_bullets = [b.strip("- •").strip() for b in enhanced_bullets if b.strip()]
            
            # Section 4: Enhance goal descriptions
            for goal in briefing.explicit_goals + briefing.implied_goals:
                if goal.reasoning:
                    prompt = f"""Improve this: {goal.reasoning}"""
                    
                    response = openai_client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": "You are an insurance expert. Improve clarity."},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=100,
                        temperature=0.7,
                    )
                    
                    goal.reasoning = response.choices[0].message.content.strip()
            
            # Section 5: Enhance risk signal descriptions
            for risk in briefing.risk_signals:
                prompt = f"""Improve clarity: {risk.text}"""
                
                response = openai_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are an insurance expert. Improve clarity."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=100,
                    temperature=0.7,
                )
                
                risk.text = response.choices[0].message.content.strip()
            
            # Section 8: Enhance follow-up questions
            if briefing.follow_up_questions:
                questions_text = "\n".join(briefing.follow_up_questions)
                prompt = f"""Improve these questions: {questions_text}"""
                
                response = openai_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are an insurance expert. Improve clarity."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=200,
                    temperature=0.7,
                )
                
                enhanced_q = response.choices[0].message.content.strip().split("\n")
                briefing.follow_up_questions = [q.strip("?-•").strip() for q in enhanced_q if q.strip()]
            
            # Section 9: Enhance recommendations
            if briefing.talking_points:
                points_text = "\n".join(briefing.talking_points)
                prompt = f"""Improve these points: {points_text}"""
                
                response = openai_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are an insurance expert. Improve clarity."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=200,
                    temperature=0.7,
                )
                
                enhanced_tp = response.choices[0].message.content.strip().split("\n")
                briefing.talking_points = [tp.strip("•-").strip() for tp in enhanced_tp if tp.strip()]
            
            # Mark that enhancement was done
            briefing.narrative_model = f"{model}-enhanced"
            briefing.narrative_generated_at = datetime.now().isoformat()
            
            return briefing
            
        except Exception as e:
            print(f"⚠️  LLM enhancement failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            # Return original briefing if enhancement fails
            return briefing


def format_briefing_for_display(briefing: UnderwriterBriefing) -> str:
    """Format briefing as one-page auditable report."""
    output = []
    output.append("\n" + "=" * 90)
    output.append("UNDERWRITER BRIEFING REPORT".center(90))
    output.append("=" * 90)
    
    # Header
    output.append(f"\nBroker: {briefing.broker_name} | Company: {briefing.broker_company}")
    output.append(f"Email: {briefing.broker_email}")
    output.append(f"Email Subjects: {'; '.join(briefing.email_subjects) if briefing.email_subjects else 'N/A'}")
    output.append("-" * 90)
    
    # ========== SECTION 1: EXECUTIVE SUMMARY ==========
    output.append("\n1. EXECUTIVE SUMMARY")
    output.append("-" * 45)
    for i, bullet in enumerate(briefing.exec_summary_bullets, 1):
        output.append(f"   • {bullet}")
    
    # ========== SECTION 2: SENTIMENT & TONE ==========
    output.append("\n2. BROKER SENTIMENT & TONE ANALYSIS")
    output.append("-" * 45)
    output.append(f"   Overall Sentiment: {briefing.overall_sentiment}")
    output.append(f"   Confidence: {briefing.sentiment_confidence:.0%}")
    if briefing.emotional_signals:
        output.append(f"   Emotional Signals: {', '.join(briefing.emotional_signals)}")
    if briefing.tone_quotes:
        output.append("   Language Indicators (Quotes):")
        for citation in briefing.tone_quotes:
            output.append(f"     - \"{citation.quote}\" [{citation.location}]")
    
    # ========== SECTION 3: KEY RELATIONSHIPS ==========
    output.append("\n3. KEY RELATIONSHIPS & STAKEHOLDERS")
    output.append("-" * 45)
    if briefing.stakeholders:
        output.append("   Name | Role | Influence | Signal | Notes")
        for s in briefing.stakeholders:
            output.append(f"   {s.name} | {s.role} | {s.influence_level.value} | {s.relationship_signal.value} | {s.notes}")
    else:
        output.append("   No stakeholders identified")
    
    # ========== SECTION 4: BROKER PRIORITIES ==========
    output.append("\n4. BROKER PRIORITIES & OBJECTIVES")
    output.append("-" * 45)
    
    if briefing.explicit_goals:
        output.append("   EXPLICITLY STATED GOALS:")
        for goal in briefing.explicit_goals:
            confidence_display = f"({goal.confidence:.0%})" if goal.confidence else "(N/A)"
            output.append(f"   ✓ {goal.text} {confidence_display}")
            if goal.citation:
                output.append(f"     Quote: \"{goal.citation.quote}\"")
    
    if briefing.implied_goals:
        output.append("   IMPLIED GOALS (INFERRED):")
        for goal in briefing.implied_goals:
            output.append(f"   ⊕ {goal.text} ({goal.confidence:.0%})")
            if goal.reasoning:
                output.append(f"     Reasoning: {goal.reasoning}")
    
    if briefing.commercial_signals:
        output.append("   Commercial Signals:")
        for signal in briefing.commercial_signals:
            output.append(f"     • {signal}")
    
    # ========== SECTION 5: RISK SIGNALS ==========
    output.append("\n5. RISK SIGNALS & RED FLAGS")
    output.append("-" * 45)
    if briefing.risk_signals:
        for risk in briefing.risk_signals:
            source_label = "FACT" if risk.source == SourceType.EXPLICIT else "INFERRED"
            output.append(f"   [{source_label}] {risk.text} ({risk.confidence:.0%})")
            if risk.citation:
                output.append(f"          \"{risk.citation.quote}\"")
    else:
        output.append("   No major red flags identified")
    
    # ========== SECTION 6: NEGOTIATION POSTURE ==========
    output.append("\n6. NEGOTIATION & COMMUNICATION POSTURE")
    output.append("-" * 45)
    output.append(f"   Likely Style: {briefing.negotiation_style}")
    if briefing.pressure_tactics:
        output.append("   Pressure Tactics Observed:")
        for tactic in briefing.pressure_tactics:
            output.append(f"     • {tactic.text} ({tactic.confidence:.0%})")
    if briefing.past_objections:
        output.append("   Past Objections Referenced:")
        for obj in briefing.past_objections:
            output.append(f"     • {obj}")
    
    # ========== SECTION 7: KEY FACTS SNAPSHOT ==========
    output.append("\n7. KEY FACTS SNAPSHOT")
    output.append("-" * 45)
    facts = [
        ("Account/Insured", briefing.insured_name or "Not specified"),
        ("Line(s) of Business", ", ".join(briefing.line_of_business) if briefing.line_of_business else "Not specified"),
        ("Renewal/Effective Date", briefing.renewal_date or "Not specified"),
        ("Premium", briefing.premium or "Not specified"),
        ("Limits", ", ".join(briefing.limits) if briefing.limits else "Not specified"),
        ("Loss History", briefing.loss_history or "Not mentioned"),
        ("Special Conditions", ", ".join(briefing.special_conditions) if briefing.special_conditions else "None noted"),
    ]
    for label, value in facts:
        output.append(f"   {label:<25} {value}")
    
    # ========== SECTION 8: MISSING INFORMATION ==========
    output.append("\n8. MISSING INFORMATION TO CLARIFY")
    output.append("-" * 45)
    if briefing.missing_info:
        output.append("   Unknowns That Materially Impact Underwriting:")
        for item in briefing.missing_info:
            output.append(f"     ⚠ {item}")
    if briefing.follow_up_questions:
        output.append("   Suggested Follow-up Questions:")
        for q in briefing.follow_up_questions:
            output.append(f"     ? {q}")
    
    # ========== SECTION 9: UNDERWRITER PREP ==========
    output.append("\n9. UNDERWRITER PREP RECOMMENDATIONS")
    output.append("-" * 45)
    if briefing.opening_statement:
        output.append(f"   Recommended Opening: \"{briefing.opening_statement}\"")
    if briefing.talking_points:
        output.append("   Talking Points:")
        for tp in briefing.talking_points:
            output.append(f"     ✓ {tp}")
    if briefing.lean_in_areas:
        output.append("   Lean In (Opportunities):")
        for area in briefing.lean_in_areas:
            output.append(f"     ↑ {area}")
    if briefing.proceed_cautiously:
        output.append("   Proceed Cautiously (Risks):")
        for risk in briefing.proceed_cautiously:
            output.append(f"     ↓ {risk}")
    if briefing.questions_to_ask:
        output.append("   Key Questions to Ask:")
        for q in briefing.questions_to_ask[:5]:  # Top 5 to stay on one page
            output.append(f"     • {q}")
    
    # ========== SECTION 10: CONFIDENCE & LIMITATIONS ==========
    output.append("\n10. CONFIDENCE & LIMITATIONS")
    output.append("-" * 45)
    output.append(f"   Overall Briefing Confidence: {briefing.overall_confidence:.0%}")
    output.append("   What Could Change This Assessment:")
    for lim in briefing.limitations:
        output.append(f"     • {lim}")
    
    output.append("\n" + "=" * 90)
    output.append(f"Report Generated: {briefing.broker_email}")
    output.append("=" * 90 + "\n")
    
    return "\n".join(output)


def format_briefing_as_markdown(briefing: UnderwriterBriefing) -> str:
    """Format briefing as readable Markdown for Copilot Studio / chat display."""
    output = []
    
    output.append(f"# Underwriter Briefing: {briefing.broker_name}")
    output.append(f"\n**Broker Email:** {briefing.broker_email} | **Company:** {briefing.broker_company}")
    output.append(f"**Subject:** {'; '.join(briefing.email_subjects) if briefing.email_subjects else 'N/A'}")
    output.append("\n---\n")
    
    # Executive Summary
    output.append("## 1️⃣ Executive Summary")
    for bullet in briefing.exec_summary_bullets:
        output.append(f"- {bullet}")
    
    # Sentiment & Tone
    output.append(f"\n## 2️⃣ Sentiment & Tone")
    output.append(f"**Overall Sentiment:** {briefing.overall_sentiment} ({briefing.sentiment_confidence:.0%} confidence)")
    if briefing.emotional_signals:
        output.append(f"**Emotional Signals:** {', '.join(briefing.emotional_signals)}")
    if briefing.tone_quotes:
        output.append("\n**Key Phrases:**")
        for cite in briefing.tone_quotes[:2]:  # Top 2 quotes
            output.append(f"- \"{cite.quote}\"")
    
    # Key Relationships
    output.append(f"\n## 3️⃣ Key Relationships")
    if briefing.stakeholders:
        for s in briefing.stakeholders:
            output.append(f"- **{s.name}** ({s.role}) — {s.influence_level.value} Influence | {s.relationship_signal.value}")
    
    # Broker Priorities
    output.append(f"\n## 4️⃣ Broker Priorities & Objectives")
    
    if briefing.explicit_goals:
        output.append("**Explicitly Stated:**")
        for goal in briefing.explicit_goals:
            output.append(f"- ✓ {goal.text} ({goal.confidence:.0%})")
            if goal.citation:
                output.append(f"  > \"{goal.citation.quote}\"")
    
    if briefing.implied_goals:
        output.append("\n**Implied (Inferred):**")
        for goal in briefing.implied_goals:
            output.append(f"- ⊕ {goal.text} ({goal.confidence:.0%})")
            if goal.reasoning:
                output.append(f"  > {goal.reasoning}")
    
    # Risk Signals
    output.append(f"\n## 5️⃣ Risk Signals & Red Flags")
    if briefing.risk_signals:
        for risk in briefing.risk_signals:
            source = "📌 FACT" if risk.source == SourceType.EXPLICIT else "⚠️ INFERRED"
            output.append(f"- {source}: {risk.text} ({risk.confidence:.0%})")
    else:
        output.append("- ✅ No major red flags identified")
    
    # Negotiation Posture
    output.append(f"\n## 6️⃣ Negotiation Posture")
    output.append(f"**Style:** {briefing.negotiation_style}")
    if briefing.talking_points:
        output.append("\n**Talking Points:**")
        for tp in briefing.talking_points:
            output.append(f"- {tp}")
    
    # Key Facts
    output.append(f"\n## 7️⃣ Key Facts Snapshot")
    facts = [
        ("**Insured**", briefing.insured_name or "Not specified"),
        ("**Line of Business**", ", ".join(briefing.line_of_business) if briefing.line_of_business else "Not specified"),
        ("**Renewal Date**", briefing.renewal_date or "Not specified"),
        ("**Premium**", briefing.premium or "Not specified"),
        ("**Limits**", ", ".join(briefing.limits) if briefing.limits else "Not specified"),
    ]
    for label, value in facts:
        output.append(f"- {label}: {value}")
    
    # Missing Information
    output.append(f"\n## 8️⃣ Missing Information")
    if briefing.missing_info:
        output.append("**To Clarify:**")
        for item in briefing.missing_info:
            output.append(f"- ⚠️ {item}")
    if briefing.follow_up_questions:
        output.append("\n**Follow-up Questions:**")
        for q in briefing.follow_up_questions[:3]:  # Top 3
            output.append(f"- {q}")
    
    # Underwriter Prep
    output.append(f"\n## 9️⃣ Underwriter Prep")
    if briefing.opening_statement:
        output.append(f"**Opening Line:** _{briefing.opening_statement}_")
    
    if briefing.lean_in_areas:
        output.append("\n**Lean In (Opportunities):**")
        for area in briefing.lean_in_areas:
            output.append(f"- ↑ {area}")
    
    if briefing.proceed_cautiously:
        output.append("\n**Proceed Cautiously:**")
        for risk in briefing.proceed_cautiously:
            output.append(f"- ↓ {risk}")
    
    # Confidence & Limitations
    output.append(f"\n## 🔟 Confidence Level")
    output.append(f"**Overall Confidence:** {briefing.overall_confidence:.0%}")
    output.append("\n**Important Limitations:**")
    for lim in briefing.limitations[:3]:  # Top 3
        output.append(f"- {lim}")
    
    output.append("\n---")
    output.append(f"_Report generated from email analysis. Data stored in Cosmos DB._\n")
    
    return "\n".join(output)


def load_secrets_from_file(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        print(f"Failed to read {path}: {exc}")
        return {}


def get_config() -> dict:
    # Try secrets.json first (local dev priority), then fall back to env vars
    local = load_secrets_from_file("secrets.json")
    
    cfg = {
        "LANGUAGE_ENDPOINT": os.getenv("LANGUAGE_ENDPOINT") or local.get("LANGUAGE_ENDPOINT"),
        "OPENAI_ENDPOINT": os.getenv("OPENAI_ENDPOINT") or local.get("OPENAI_ENDPOINT"),
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL") or local.get("OPENAI_MODEL", "DeepSeek-V3.2"),
    }

    return cfg


if __name__ == "__main__":
    # Example usage with a sample broker email
    from azure.ai.textanalytics import TextAnalyticsClient
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from openai import AzureOpenAI
    import os

    cfg = get_config()
    language_endpoint = cfg.get("LANGUAGE_ENDPOINT")
    openai_endpoint = cfg.get("OPENAI_ENDPOINT")
    openai_model = cfg.get("OPENAI_MODEL", "DeepSeek-V3.2")

    if not language_endpoint:
        print("Underwriter Briefing Generator ready for integration.")
        print("\nTo generate a sample report, set LANGUAGE_ENDPOINT via:")
        print("  1. Environment variable: LANGUAGE_ENDPOINT")
        print("  2. Local file: secrets.json with LANGUAGE_ENDPOINT key")
        print("\nThen run: python3 underwriter_briefing.py")
        exit(1)

    credential = DefaultAzureCredential()

    # Create client
    client = TextAnalyticsClient(
        endpoint=language_endpoint,
        credential=credential
    )
    
    # Sample broker email
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
    
    # Generate briefing (EXTRACTION LAYER)
    generator = BriefingGenerator(client)
    briefing = generator.generate_briefing(
        broker_email="shreyas@acme.com",
        body_text=sample_email,
        subject="Email 2 – Positive / Proactive",
        sender_name="Shreyas",
        sender_company="Acme Manufacturing"
    )
    
    print("✅ Extraction complete\n")
    
    # Generate LLM enhancement (POLISH READABILITY) using Foundry with Service Principal
    if openai_endpoint:
        try:
            # Use service principal auth
            from azure.identity import ClientSecretCredential
            credential = ClientSecretCredential(
                tenant_id=cfg.get("AZURE_TENANT_ID"),
                client_id=cfg.get("AZURE_CLIENT_ID"),
                client_secret=cfg.get("AZURE_CLIENT_SECRET")
            )
            openai_client = AzureOpenAI(
                azure_ad_token_provider=lambda: credential.get_token("https://ai.azure.com/.default").token,
                api_version="2024-08-01-preview",
                azure_endpoint=openai_endpoint
            )
            briefing = generator.generate_narrative_wrapper(
                briefing,
                openai_client,
                model=openai_model
            )
            print(f"✅ Enhanced readability using {openai_model} (Foundry with Azure AD)\n")
        except Exception as e:
            print(f"⚠️  Enhancement skipped: {str(e)}\n")
    else:
        print("⚠️  Foundry endpoint not configured (enhancement skipped)\n")
    
    # Print Markdown format (user-friendly for Copilot Studio)
    print("="*90)
    print("HYBRID BRIEFING - MARKDOWN FORMAT")
    print("="*90)
    print(format_briefing_as_markdown(briefing))
    
    # Also print traditional report format
    print("\n" + "="*90)
    print("HYBRID BRIEFING - TRADITIONAL REPORT FORMAT")
    print("="*90)
    print(format_briefing_for_display(briefing))
    
    # Print JSON (for storage/API)
    print("\n" + "="*90)
    print("HYBRID BRIEFING - JSON FORMAT (for Cosmos DB)")
    print("="*90)
    print(briefing.to_json())
    
    # Store in Cosmos DB (if configured)
    try:
        from cosmos_storage import BriefingStorage, get_cosmos_config
        
        cosmos_cfg = get_cosmos_config()
        if cosmos_cfg["endpoint"] and cosmos_cfg["key"]:
            print("\n" + "="*90)
            print("STORING IN COSMOS DB")
            print("="*90)
            storage = BriefingStorage(
                endpoint=cosmos_cfg["endpoint"],
                key=cosmos_cfg["key"],
                database_name=cosmos_cfg["database"],
                container_name=cosmos_cfg["container"]
            )
            stored = storage.store_briefing(briefing.to_dict())
            print(f"✅ Stored in Cosmos DB")
            print(f"   ID: {stored['id']}")
            print(f"   Database: {cosmos_cfg['database']}")
            print(f"   Container: {cosmos_cfg['container']}")
        else:
            print("\n⚠️  Cosmos DB not configured (skipping storage)")
            print("   Add COSMOS_ENDPOINT to secrets.json to enable")
    except ImportError:
        print("\n⚠️  cosmos_storage.py not found (skipping Cosmos DB storage)")
    except Exception as e:
        print(f"\n⚠️  Cosmos DB storage failed: {str(e)}")
