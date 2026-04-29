# What Comes From Azure vs. What's Built Locally

## **The Breakdown**

### **1. Sentiment Classification**
| Aspect | Source | Details |
|--------|--------|---------|
| **Core Capability** | ✅ **Azure Language Service** | Azure Sentiment Analysis API analyzes the entire email and returns: `positive`, `neutral`, `negative`, `mixed` |
| **Confidence Score** | ✅ **Azure Language Service** | Azure returns 3 confidence scores: `positive_score`, `neutral_score`, `negative_score` (each 0.0-1.0) |
| **Local Enhancement** | ✅ **Our Code** | We take the MAX of the 3 scores (most confident classification) |
| **Emotional Signals** | ✅ **Our Code** | We apply thresholds to classify emotions: IF `positive > 0.6` THEN add "Supportive", "Collaborative" |
| **Human-Readable Label** | ✅ **Our Code** | Map "positive" → "Positive" (simple string formatting) |

**Azure API Call:**
```python
response = self.client.analyze_sentiment(documents=[body_text])
# Returns: sentiment: "positive", confidence_scores: {positive: 0.74, neutral: 0.15, negative: 0.11}
```

**Local Enhancement:**
```python
if result.confidence_scores.positive > 0.6:
    signals.extend(["Supportive", "Collaborative"])  # Our rule
```

---

### **2. Quotes from Email Body**
| Aspect | Source | Details |
|--------|--------|---------|
| **Quote Extraction** | ❌ **NOT from Azure** | Pure regex pattern matching (local) |
| **Sentence Boundary Detection** | ❌ **NOT from Azure** | Regex: `[^.!?]*keyword[^.!?]*[.!?]` finds full sentence |
| **Keyword Matching** | ❌ **NOT from Azure** | Local patterns for "urgent", "renewal", "expect", etc. |

**Our Code (100% local):**
```python
def find_quote(self, keyword: str, text: str) -> Optional[Citation]:
    pattern = rf"[^.!?]*\b{re.escape(keyword)}\b[^.!?]*[.!?]"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        quote = match.group(0).strip()
        return Citation(quote=quote, location="Email body")
```

**Example:**
```
Input: keyword="renewal", email text includes "...completed our initial review of the Acme Manufacturing renewal."
Output: Citation(
    quote="Wanted to let you know we've completed our initial review of the Acme Manufacturing renewal.",
    location="Email body"
)
```

---

### **3. Confidence Levels**
| Aspect | Source | Details |
|--------|--------|---------|
| **Sentiment Confidence** | ✅ **Azure Language Service** | Direct from API (0.7–0.95 range) |
| **Keyword Match Confidence** | ❌ **NOT from Azure** | Hardcoded in our code: `confidence=0.95` for urgency keywords |
| **Financial Amount Confidence** | ❌ **NOT from Azure** | Hardcoded: `confidence=0.9` for regex `$` matches |
| **Inferred Goal Confidence** | ❌ **NOT from Azure** | Hardcoded: `confidence=0.80` for sentiment-based inferences |
| **Overall Confidence** | ❌ **NOT from Azure** | Our code: `sum(all_scores) / len(all_scores)` |

**Azure provides:**
```python
result.confidence_scores.positive  # 0.74
result.confidence_scores.neutral   # 0.15
result.confidence_scores.negative  # 0.11
```

**We add:**
```python
# If "urgent" keyword found
ExtractedFact(text="urgent", confidence=0.95, source=EXPLICIT)

# If sentiment is "Positive" 
ExtractedFact(text="Build collaborative relationship", confidence=0.80, source=INFERRED)

# Overall
overall = (0.74 + 0.95 + 0.80) / 3 = 0.83 ≈ 83%
```

---

### **4. Explicit vs Inferred Separation**
| Aspect | Source | Details |
|--------|--------|---------|
| **Source Type Enum** | ❌ **NOT from Azure** | Our dataclass defines `SourceType.EXPLICIT` vs `INFERRED` |
| **Explicit Detection** | ❌ **NOT from Azure** | Regex patterns for keywords like "urgent", "renewal", "$" amounts |
| **Inferred Detection** | ❌ **NOT from Azure** | Rule-based: IF sentiment="Positive" THEN infer="collaboration" |
| **Confidence Capping** | ❌ **NOT from Azure** | Our validation: Inferred facts capped at 0.95 |
| **Reasoning Requirement** | ❌ **NOT from Azure** | Our validation: Inferred facts MUST have reasoning field |

**Our Code (100% local business logic):**
```python
# EXPLICIT (from email text)
ExtractedFact(
    text="expect",
    source=SourceType.EXPLICIT,  # ← We define this
    confidence=0.95,              # ← We set this
    citation=find_quote("expect", body_text),  # ← We find this
)

# INFERRED (from sentiment analysis)
if sentiment == "Positive":
    ExtractedFact(
        text="Build collaborative relationship",
        source=SourceType.INFERRED,  # ← We define this
        confidence=0.80,             # ← We cap it
        reasoning="Positive sentiment + collaborative language suggests relationship-focused engagement",  # ← We require this
    )
```

**Validation (our code):**
```python
def validate(self) -> bool:
    if self.source == SourceType.INFERRED:
        assert self.reasoning, "Inferred facts must have reasoning"
        assert self.confidence <= 0.95, "Inferred facts capped at 95%"
    return True
```

---

### **5. Missing Information**
| Aspect | Source | Details |
|--------|--------|---------|
| **Missing Info Detection** | ❌ **NOT from Azure** | Hardcoded checklist (could be enhanced) |
| **Smart Gap Analysis** | ❌ **NOT from Azure** | Could use Azure Key Phrase Extraction + domain rules |

**Current Implementation (Hardcoded):**
```python
briefing.missing_info = [
    "Specific line(s) of business not clearly stated",
    "Coverage limits and deductibles not specified",
    "Loss history/claims experience not provided",
    "Current premium and terms not mentioned",
    "Special coverages or endorsements not addressed",
]
```

**Could be Enhanced With Azure:**
```python
# Extract key phrases via Azure API
response = client.extract_key_phrases(documents=[body_text])
phrases = response[0].key_phrases

# Compare against required fields
required_fields = {
    "line of business": False,
    "coverage limits": False,
    "loss history": False,
    # ...
}

for phrase in phrases:
    if "line of business" in phrase.lower():
        required_fields["line of business"] = True

# Populate missing_info based on what wasn't found
for field, found in required_fields.items():
    if not found:
        missing_info.append(f"{field} not mentioned")
```

---

### **6. Governance Alignment with Cloud Adoption Framework**

| Principle | Source | Implementation |
|-----------|--------|-----------------|
| **Explainability** | ❌ **NOT from Azure** | Our `reasoning` field on inferred facts |
| **Auditability** | ❌ **NOT from Azure** | Our `Citation` tracking (quotes + locations) |
| **Uncertainty Quantification** | ✅ **Partially Azure** | Confidence scores (both Azure API + our rules) |
| **Bias Mitigation** | ❌ **NOT from Azure** | Our confidence capping for inferred facts |
| **Traceability** | ❌ **NOT from Azure** | Our `source` field (EXPLICIT vs INFERRED) |
| **Data Minimization** | ❌ **NOT from Azure** | Our selective extraction (only key entities) |
| **Compliance Logging** | ❌ **NOT from Azure** | Our structured JSON output ready for audit logs |

**Governance Features (All Local):**

```python
# 1. EXPLAINABILITY
ExtractedFact(
    text="Build collaborative relationship",
    source=SourceType.INFERRED,
    reasoning="Positive sentiment + collaborative language suggests relationship-focused engagement"  # ← Explains the inference
)

# 2. AUDITABILITY
Citation(
    quote="We're aligned on next steps and expect to have an updated indication ready shortly.",
    location="Email body"  # ← Traceable to source
)

# 3. UNCERTAINTY QUANTIFICATION
confidence=0.80  # ← Explicit uncertainty measure

# 4. BIAS MITIGATION
assert self.confidence <= 0.95, "Inferred facts capped at 95%"  # ← Prevents overconfidence

# 5. TRACEABILITY
source=SourceType.INFERRED  # ← Distinguishes claimed vs inferred

# 6. COMPLIANCE LOGGING
briefing.to_json()  # ← Full audit trail in structured format
```

---

### **7. Strict Grounding & Self-Validation**

| Aspect | Source | Details |
|--------|--------|---------|
| **Fact Validation** | ❌ **NOT from Azure** | Our `ExtractedFact.validate()` method |
| **Confidence Range Checks** | ❌ **NOT from Azure** | Assert `0 <= confidence <= 1` |
| **Source Consistency Checks** | ❌ **NOT from Azure** | IF source=INFERRED THEN reasoning must exist |
| **Citation Requirement** | ❌ **NOT from Azure** | Explicit facts should have citations |
| **Type Safety** | ❌ **NOT from Azure** | Dataclass with typed fields |

**Our Validation Code:**
```python
@dataclass
class ExtractedFact:
    text: str
    category: str
    source: SourceType  # ← Type-safe enum
    confidence: float
    citation: Optional[Citation] = None
    reasoning: Optional[str] = None
    
    def validate(self) -> bool:
        # CHECK 1: Confidence must be 0-1
        assert 0 <= self.confidence <= 1, "Confidence must be 0-1"
        
        # CHECK 2: Inferred facts must have reasoning
        if self.source == SourceType.INFERRED:
            assert self.reasoning, "Inferred facts must have reasoning"
            assert self.confidence <= 0.95, "Inferred facts capped at 95%"
        
        # CHECK 3: Explicit facts should have citations
        if self.source == SourceType.EXPLICIT:
            # Optional: could require citation
            pass
        
        return True
```

---

## **Summary: What Azure Does vs What We Build**

### **Azure Language Service Provides (The 20%)**
✅ Sentiment Analysis
- Input: Email text
- Output: Sentiment (positive/neutral/negative/mixed) + 3 confidence scores
- Cost: $0.002 per email

✅ Named Entity Recognition (NER)
- Input: Email text
- Output: People, Organizations, Emails, Phone Numbers, Addresses
- Cost: $0.002 per email (same API call)

### **We Build On Top (The 80%)**
❌ Explicit vs Inferred separation
❌ Confidence capping for inferences
❌ Reasoning requirement enforcement
❌ Quote extraction & localization
❌ Risk signal detection (urgency, pricing)
❌ Negotiation style classification
❌ Missing information analysis
❌ Governance compliance framework
❌ Self-validation & fact-checking
❌ Structured output formatting

---

## **Data Flow Diagram**

```
EMAIL INPUT
    ↓
┌─────────────────────────────────────┐
│  Azure Language Service             │
│  (Cost: $0.002)                     │
│                                      │
│  ✅ Sentiment Analysis API          │
│     └─ Returns: sentiment +          │
│        3 confidence scores           │
│                                      │
│  ✅ NER API                         │
│     └─ Returns: people, orgs,       │
│        emails, phone numbers         │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Local Processing (Our Code)        │
│  (Cost: Free / microseconds)        │
│                                      │
│  Regex Extraction:                  │
│  ❌ Urgency keywords                 │
│  ❌ Pricing signals                  │
│  ❌ Quote extraction                 │
│  ❌ Sentence boundaries              │
│                                      │
│  Rule-Based Inference:              │
│  ❌ IF sentiment=Pos → collaboration │
│  ❌ Talking points per sentiment     │
│  ❌ Negotiation style                │
│                                      │
│  Governance Layer:                  │
│  ❌ Source tracking (EXPLICIT/INFERRED) │
│  ❌ Confidence capping               │
│  ❌ Reasoning requirements           │
│  ❌ Citation tracking                │
│  ❌ Fact validation                  │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Outputs (All Local)                │
│                                      │
│  ✅ Markdown (Copilot Studio)       │
│  ✅ JSON (Cosmos DB)                │
│  ✅ Human-readable report            │
└─────────────────────────────────────┘
```

---

## **Why This Architecture?**

| Question | Answer |
|----------|--------|
| **Why not use LLMs?** | We use deterministic rules + Azure AI for speed, auditability, and cost ($0.004/email vs $0.01+ per LLM call) |
| **Why not 100% Azure?** | Azure doesn't provide explicit/inferred separation, reasoning requirements, or governance validation |
| **Why not 100% local?** | Local NLP is unreliable; Azure's ML models are trained on billions of texts |
| **Why Sentiment + NER?** | These are the only two Azure APIs we actually *need* to generate the briefing; everything else is rules |

---

## **Potential Azure Enhancements (Future)**

If we wanted to make the system *smarter*, we could add:

1. **Key Phrase Extraction** → Better missing info detection
2. **Abstractive Summarization** → Auto-generate executive summary
3. **Custom NER Models** → Insurance-specific entity extraction (Policy #, Premium amounts, etc.)
4. **Question Answering API** → Match common underwriting questions to email content
5. **Language Detection** → Handle multilingual broker emails

But for now, the current setup is **optimal** because:
- ✅ Low cost ($0.004/email)
- ✅ Fast (milliseconds)
- ✅ Fully auditable
- ✅ Deterministic (no hallucinations)
- ✅ Enterprise-ready

