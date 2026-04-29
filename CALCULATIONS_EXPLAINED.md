# How Underwriter Briefing Calculates All Elements

## 1. **Executive Summary with Fixed Bullets**
**Location:** [Lines 365-376](underwriter_briefing.py#L365-L376)

```python
briefing.exec_summary_bullets = [
    f"Purpose: {subject}",                                              # Input: email subject
    f"Broker Stance: {sentiment} tone with {', '.join(emotional_signals) if emotional_signals else 'neutral signals'}",
    f"Key Contact: {sender_name} from {sender_company}",               # Input: NER extraction
    f"Sentiment Confidence: {sentiment_conf:.0%} (based on email tone analysis)",  # Azure API
    f"Status: Requires underwriting review and follow-up",
]
```

**Calculation:**
- **Sentiment**: Direct output from `analyze_sentiment_and_tone()` (Azure Language Service)
- **Emotional Signals**: Derived from confidence score thresholds (lines 308-313)
- **Key Contact**: Extracted via Named Entity Recognition (NER) for PERSON entities

---

## 2. **Sentiment Classification**
**Location:** [Lines 295-320](underwriter_briefing.py#L295-L320) - `analyze_sentiment_and_tone()`

```python
def analyze_sentiment_and_tone(self, text: str) -> tuple[str, float, list[str]]:
    response = self.client.analyze_sentiment(documents=[text])  # AZURE API CALL
    result = response[0]
    
    sentiment = result.sentiment  # Returns: "positive", "neutral", "negative", "mixed"
    confidence = max(
        result.confidence_scores.positive,
        result.confidence_scores.neutral,
        result.confidence_scores.negative
    )
    
    # Map to human-readable format
    sentiment_map = {
        "positive": "Positive",
        "neutral": "Neutral",
        "negative": "Negative",
        "mixed": "Mixed",
    }
    return sentiment_map.get(sentiment, "Unknown"), confidence, signals
```

**Calculation:**
- **Source:** Azure Cognitive Services Sentiment Analysis API
- **Input:** Raw email body text
- **Output:** Sentiment string + confidence score (0.0–1.0) + emotional signals list
- **Confidence Calculation:** Takes the MAX of three scores (positive, neutral, negative probabilities)

---

## 3. **Quotes from Email Body**
**Location:** [Lines 239-256](underwriter_briefing.py#L239-L256) - `find_quote()`

```python
def find_quote(self, keyword: str, text: str) -> Optional[Citation]:
    """Find sentence containing keyword."""
    pattern = rf"[^.!?]*\b{re.escape(keyword)}\b[^.!?]*[.!?]"
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        quote = match.group(0).strip()
        return Citation(quote=quote, location="Email body")
    return None
```

**Calculation:**
- **Pattern matching:** Regex finds sentence boundary containing keyword
- **Extraction:** Captures full sentence including keyword
- **Storage:** Wrapped in `Citation` dataclass with location metadata

**Example:**
```
Input keyword: "renewal"
Email text: "Wanted to let you know we've completed our initial review of the Acme Manufacturing renewal."
Output: Citation(quote="Wanted to let you know we've completed our initial review of the Acme Manufacturing renewal.", location="Email body")
```

---

## 4. **Confidence Levels**
**Location:** [Lines 506-511](underwriter_briefing.py#L506-L511) - Overall confidence aggregation

```python
# Aggregate all confidence scores
all_confidences = [
    sentiment_conf,                          # From sentiment analysis
    *[f.confidence for f in briefing.explicit_goals],
    *[f.confidence for f in briefing.implied_goals],
    *[f.confidence for f in briefing.risk_signals]
]
briefing.overall_confidence = (
    sum(all_confidences) / len(all_confidences)
) if all_confidences else 0.5
```

**Calculation:**
- **Method:** Simple average (arithmetic mean) of all confidence scores
- **Range:** 0.0–1.0
- **Components:**
  - Sentiment confidence (from Azure API)
  - Each explicit goal confidence (0.85–0.95, tuned by category)
  - Each inferred goal confidence (capped at 0.80, due to inference uncertainty)
  - Each risk signal confidence (0.85–0.90)

**Example:**
```
Sentiment: 0.74
Explicit goal (renewal): 0.95
Inferred goal (collaboration): 0.80
Risk signal (none detected): N/A
Overall = (0.74 + 0.95 + 0.80) / 3 = 0.83 ≈ 83%
```

---

## 5. **Explicit Separation: Inferred vs Stated**
**Location:** [Lines 45-65](underwriter_briefing.py#L45-L65) - `ExtractedFact` dataclass with `SourceType`

```python
@dataclass
class ExtractedFact:
    text: str
    category: str
    source: SourceType              # ← EXPLICIT control here
    confidence: float
    citation: Optional[Citation] = None
    reasoning: Optional[str] = None
    
    def validate(self) -> bool:
        if self.source == SourceType.INFERRED:
            assert self.reasoning, "Inferred facts MUST have reasoning"
            assert self.confidence <= 0.95, "Inferred facts capped at 95%"
        return True
```

**Calculation:**
- **Explicit (STATED):** 
  - Source: Direct regex/keyword matching from email
  - Confidence: 0.85–0.95
  - Citation: Always included
  - No reasoning field
  - Example: "urgent" keyword detected in email → Explicit
  
- **Inferred (REASONING-BASED):**
  - Source: Derived from sentiment, tone, context
  - Confidence: Capped at 0.80 (never exceeds 0.95)
  - Citation: May be null
  - Reasoning: REQUIRED field with explanation
  - Example: "Positive sentiment suggests collaborative intent" → Inferred

**Validation Rule:**
```python
if source == SourceType.INFERRED:
    assert reasoning is not None, "Must explain inference"
    assert confidence <= 0.95, "Inferred facts are less certain"
```

---

## 6. **Missing Information**
**Location:** [Lines 489–501](underwriter_briefing.py#L489-L501)

```python
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
    # ... etc
]
```

**Calculation:**
- **Hardcoded defaults** (could be enhanced with):
  - Extraction of coverage-related keywords
  - Comparison against required fields checklist
  - Gap analysis vs. historical data

---

## 7. **Explicit Goal Extraction**
**Location:** [Lines 207–237](underwriter_briefing.py#L207-L237) - `extract_key_urgency_signals()`

```python
def extract_key_urgency_signals(self, text: str) -> list[ExtractedFact]:
    """Extract explicit urgency/timeline signals."""
    urgency_patterns = [
        (r"\b(urgent|ASAP|immediate|by\s+\w+day|deadline|as soon as|this week|today|tomorrow)\b", "timeline"),
        (r"\b(expect|expiring|renewal|effective|binding|by end of)\b", "renewal_signal"),
    ]
    
    facts = []
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
```

**Calculation:**
- **Pattern matching:** Regex searches for urgency/renewal keywords
- **Confidence:** Fixed at 0.95 (keyword match = very high confidence)
- **Citation:** Automatically extracted via `find_quote()`
- **Source:** Always `EXPLICIT` (keyword-based, not inferred)

**Example:**
```
Email text: "We expect to have an indication ready shortly."
Pattern match: "expect"
Result: ExtractedFact(
    text="expect",
    category="renewal_signal",
    source=SourceType.EXPLICIT,
    confidence=0.95,
    citation=Citation(quote="We expect to have an indication ready shortly.", location="Email body")
)
```

---

## 8. **Inferred Goal Extraction**
**Location:** [Lines 424–442](underwriter_briefing.py#L424-L442)

```python
if sentiment == "Positive":
    briefing.implied_goals.append(ExtractedFact(
        text="Build collaborative relationship",
        category="relationship_goal",
        source=SourceType.INFERRED,
        confidence=0.80,
        reasoning="Positive sentiment + collaborative language suggests relationship-focused engagement"
    ))
elif sentiment == "Negative":
    briefing.implied_goals.append(ExtractedFact(
        text="Resolve conflict or address concerns",
        category="issue_resolution",
        source=SourceType.INFERRED,
        confidence=0.75,
        reasoning="Negative sentiment detected; likely addressing specific concerns or pressure"
    ))
```

**Calculation:**
- **Rule-based inference:** IF sentiment == "Positive" THEN implied_goal = "collaboration"
- **Confidence:** 0.75–0.80 (less certain than explicit statements)
- **Reasoning:** ALWAYS included (required by validation)
- **Source:** Always `INFERRED`

---

## 9. **Risk Signals Detection**
**Location:** [Lines 263–290](underwriter_briefing.py#L263-L290) - `extract_pricing_signals()`

```python
def extract_pricing_signals(self, text: str) -> list[ExtractedFact]:
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
```

**Calculation:**
- **Pattern 1:** Keyword matching for pricing language
- **Pattern 2:** Regex for dollar amounts (`$1,234.56M`, `$500K`, etc.)
- **Confidence:** 0.9 (keyword/amount detected)
- **Citation:** Sentence containing the match

---

## 10. **Negotiation Style Determination**
**Location:** [Lines 453–471](underwriter_briefing.py#L453-L471)

```python
if sentiment == "Positive":
    briefing.negotiation_style = "Collaborative"
    talking_points = [
        "Emphasize partnership approach",
        "Highlight mutual benefits",
        "Show understanding of their priorities",
    ]
elif sentiment == "Negative":
    briefing.negotiation_style = "Defensive/Problem-solving"
    talking_points = [
        "Address concerns directly",
        "Clarify any misunderstandings",
        "Propose concrete solutions",
    ]
else:
    briefing.negotiation_style = "Exploratory"
    talking_points = [
        "Gather more information",
        "Understand their specific needs",
        "Explore alignment opportunities",
    ]
```

**Calculation:**
- **Rule-based:** Sentiment score determines style
- **Talking points:** Hardcoded per sentiment class (could be enhanced)
- **Logic:** Simple if/elif/else on sentiment classification

---

## 11. **Entity Extraction (Stakeholders)**
**Location:** [Lines 330–348](underwriter_briefing.py#L330-L348) - `extract_entities()`

```python
def extract_entities(self, text: str) -> dict:
    """Extract NER entities via Azure API."""
    response = self.client.recognize_entities(documents=[text])  # AZURE NER API
    result = response[0]
    
    summary = {
        "people": [],
        "organizations": [],
        "emails": [],
        "phones": [],
    }
    
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
```

**Calculation:**
- **Source:** Azure Cognitive Services Named Entity Recognition (NER)
- **Categories:** PERSON, ORGANIZATION, EMAIL, PHONENUMBER
- **Confidence:** Individual entities have confidence scores (not extracted here, but available)
- **Deduplication:** Implicit (sets later if needed)

---

## 12. **Data Storage & Serialization**
**Location:** [Lines 104–195](underwriter_briefing.py#L104-L195) - `to_dict()` and `to_json()`

```python
def to_dict(self) -> dict:
    return {
        "metadata": {
            "broker_email": self.broker_email,
            "broker_name": self.broker_name,
            "broker_company": self.broker_company,
            "email_subjects": self.email_subjects,
        },
        "sections": {
            "1_executive_summary": {...},
            "2_sentiment_and_tone": {...},
            "3_key_relationships": {...},
            # ... all 10 sections
        }
    }

def to_json(self) -> str:
    return json.dumps(self.to_dict(), indent=2, default=str)
```

**Storage Path:**
1. **In Memory:** UnderwriterBriefing dataclass
2. **JSON String:** Via `to_json()`
3. **Cosmos DB:** Store JSON document with:
   - `id`: broker_email + timestamp
   - `partition_key`: broker_company
   - Full briefing as document

---

## 13. **Validation & Self-Checks**
**Location:** [Lines 54–63](underwriter_briefing.py#L54-L63) - `ExtractedFact.validate()`

```python
def validate(self) -> bool:
    # Check 1: Confidence must be 0-1
    assert 0 <= self.confidence <= 1, "Confidence must be 0-1"
    
    # Check 2: Inferred facts MUST have reasoning
    if self.source == SourceType.INFERRED:
        assert self.reasoning, "Inferred facts must have reasoning"
        assert self.confidence <= 0.95, "Inferred facts capped at 95%"
    
    return True
```

**Governance Alignment:**
- ✅ **Explainability:** Reasoning required for inferences
- ✅ **Auditability:** Source tracking (explicit vs inferred)
- ✅ **Uncertainty quantification:** Confidence scores
- ✅ **Bias mitigation:** Capped confidence for inferences
- ✅ **Traceability:** Citations point to source text

---

## **Summary: Data Flow**

```
EMAIL INPUT
    ↓
[Azure Language Service]
    ├─ Sentiment Analysis → sentiment, confidence
    └─ NER → people, organizations, emails
    ↓
[Regex Pattern Matching]
    ├─ Urgency signals (EXPLICIT)
    ├─ Pricing signals (EXPLICIT)
    └─ Quotes extraction
    ↓
[Rule-Based Inference]
    ├─ Goals (from sentiment)
    ├─ Negotiation style
    └─ Confidence aggregation
    ↓
[Validation]
    ├─ Confidence range checks
    ├─ Reasoning requirements
    └─ Source tracking
    ↓
[Output Formats]
    ├─ Markdown (for Copilot Studio)
    ├─ JSON (for Cosmos DB)
    └─ Human-readable report
```

---

## **Confidence Score By Type**

| Fact Type | Source | Confidence | Reasoning Required? |
|-----------|--------|------------|-------------------|
| Sentiment | Azure API | Direct (0.7–0.95) | No |
| Urgency keyword | Regex match | 0.95 | No |
| Pricing mention | Regex match | 0.90 | No |
| Entity (person/org) | Azure NER | 0.85+ | No |
| Inferred goal | Rule-based | 0.75–0.80 | **YES** |
| Risk signal | Regex/API | 0.85–0.90 | No |

