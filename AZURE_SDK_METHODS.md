# Azure Language Service SDK Methods: What We COULD Be Using

## **What's Available in `azure-ai-textanalytics` SDK**

### **1. Sentence-Level Sentiment (Not Just Document-Level)**

**What Azure provides:**
```python
from azure.ai.textanalytics import TextAnalyticsClient

response = self.client.analyze_sentiment(
    documents=[body_text],
    language="en"
)
result = response[0]

# Document-level
print(result.sentiment)  # "positive"
print(result.confidence_scores)  # positive: 0.95, neutral: 0.02, negative: 0.03

# ALSO returns SENTENCE-LEVEL (what we're NOT using)
for sentence in result.sentences:
    print(f"Sentence: '{sentence.text}'")
    print(f"  Sentiment: {sentence.sentiment}")
    print(f"  Confidence: {sentence.confidence_scores}")
    # Output:
    # Sentence: 'We're aligned on next steps'
    #   Sentiment: positive
    #   Confidence: positive: 0.96, neutral: 0.02, negative: 0.02
```

**What we currently do:**
```python
# Only extract document-level
sentiment = result.sentiment  # Single "positive" for whole email
confidence = max(result.confidence_scores.positive, ...)

# We IGNORE result.sentences completely
```

**Why we should use it:**
```python
def generate_better_reasoning(self, body_text: str) -> str:
    """Generate reasoning from sentence-level analysis."""
    response = self.client.analyze_sentiment(documents=[body_text], language="en")
    result = response[0]
    
    positive_sentences = [s for s in result.sentences if s.sentiment == "positive"]
    negative_sentences = [s for s in result.sentences if s.sentiment == "negative"]
    
    # NOW we can say:
    if len(positive_sentences) >= len(result.sentences) * 0.75:
        return f"Strong positive sentiment: {len(positive_sentences)}/{len(result.sentences)} sentences are positive (avg confidence: {sum(s.confidence_scores.positive for s in positive_sentences) / len(positive_sentences):.0%})"
    else:
        return f"Mixed sentiment: {len(positive_sentences)} positive, {len(negative_sentences)} negative out of {len(result.sentences)} total"
```

---

### **2. Opinion Mining (Aspect-Based Sentiment)**

**What Azure provides:**
```python
response = self.client.analyze_sentiment(
    documents=[body_text],
    language="en",
    include_opinion_mining=True  # ← Enable this!
)
result = response[0]

# For each sentence, get opinions about specific targets/aspects
for sentence in result.sentences:
    print(f"Sentence: {sentence.text}")
    
    for mined_opinion in sentence.mined_opinions:
        target = mined_opinion.target
        assessments = mined_opinion.assessments
        
        print(f"  Target: '{target.text}' (confidence: {target.confidence_score:.0%})")
        for assessment in assessments:
            print(f"    Assessment: '{assessment.text}' (sentiment: {assessment.sentiment}, confidence: {assessment.confidence_score:.0%})")

# Output example:
# Sentence: "We're aligned on next steps and expect to have an updated indication ready shortly"
#   Target: 'alignment' (confidence: 0.92)
#     Assessment: 'good' (sentiment: positive, confidence: 0.94)
#   Target: 'updated indication' (confidence: 0.88)
#     Assessment: 'ready' (sentiment: positive, confidence: 0.91)
```

**What we currently do:**
```python
# We don't use opinion mining at all
# We just hardcode: "if sentiment == positive, assume collaboration goal"
```

**Why we should use it:**
```python
def extract_opinion_based_reasoning(self, body_text: str) -> dict:
    """Extract what the email's sentiment is ABOUT."""
    response = self.client.analyze_sentiment(
        documents=[body_text],
        language="en",
        include_opinion_mining=True
    )
    result = response[0]
    
    opinions = {}
    for sentence in result.sentences:
        for mined_opinion in sentence.mined_opinions:
            target_text = mined_opinion.target.text.lower()
            sentiment = sentence.sentiment
            confidence = mined_opinion.target.confidence_score
            
            if target_text not in opinions:
                opinions[target_text] = {"sentiment": sentiment, "confidence": confidence, "count": 0}
            opinions[target_text]["count"] += 1
    
    return opinions

# Returns:
# {
#   "alignment": {"sentiment": "positive", "confidence": 0.92, "count": 1},
#   "collaboration": {"sentiment": "positive", "confidence": 0.94, "count": 1},
#   "indication": {"sentiment": "positive", "confidence": 0.91, "count": 1},
# }

# NOW we can generate real reasoning:
if "collaboration" in opinions and opinions["collaboration"]["sentiment"] == "positive":
    reasoning = f"Email explicitly expresses positive sentiment about collaboration (confidence: {opinions['collaboration']['confidence']:.0%}), not just overall positive tone"
```

---

### **3. Entity Confidence Scores**

**What Azure provides:**
```python
response = self.client.recognize_entities(documents=[body_text])
result = response[0]

for entity in result.entities:
    print(f"Entity: {entity.text}")
    print(f"  Category: {entity.category}")
    print(f"  Confidence: {entity.confidence_score}")  # ← We ignore this!
    print(f"  Offset: {entity.offset}")

# Output:
# Entity: Shreyas
#   Category: PERSON
#   Confidence: 0.98
# Entity: Acme Manufacturing
#   Category: ORGANIZATION
#   Confidence: 0.96
```

**What we currently do:**
```python
for ent in getattr(result, "entities", []):
    category = (ent.category or "").lower()
    if category == "person":
        summary["people"].append(ent.text)  # ← We completely ignore ent.confidence_score
```

**Why we should use it:**
```python
def extract_high_confidence_entities(self, body_text: str, min_confidence: float = 0.8) -> dict:
    """Only extract entities we're confident about."""
    response = self.client.recognize_entities(documents=[body_text])
    result = response[0]
    
    entities = {
        "people": [],
        "organizations": [],
    }
    
    for entity in result.entities:
        if entity.confidence_score < min_confidence:
            continue  # Skip uncertain entities
        
        category = entity.category.lower()
        if category == "person":
            entities["people"].append({
                "text": entity.text,
                "confidence": entity.confidence_score
            })
        elif category == "organization":
            entities["organizations"].append({
                "text": entity.text,
                "confidence": entity.confidence_score
            })
    
    return entities

# Now we can adjust our confidence scores based on NER confidence
stakeholder_confidence = entity_confidence * sentiment_confidence
```

---

### **4. Key Phrase Extraction**

**What Azure provides:**
```python
response = self.client.extract_key_phrases(documents=[body_text], language="en")
result = response[0]

key_phrases = result.key_phrases
print(key_phrases)
# Output: ["Acme Manufacturing renewal", "initial review", "well organized submission", "updated indication", "collaboration"]
```

**What we currently do:**
```python
# We hardcode missing_info checklist, completely ignoring actual content
briefing.missing_info = [
    "Specific line(s) of business not clearly stated",  # ← Hardcoded
    "Coverage limits and deductibles not specified",     # ← Hardcoded
    "Loss history/claims experience not provided",       # ← Hardcoded
]
```

**Why we should use it:**
```python
def detect_missing_information(self, body_text: str) -> list:
    """Extract what's ACTUALLY missing from the email."""
    response = self.client.extract_key_phrases(documents=[body_text], language="en")
    key_phrases = response[0].key_phrases
    phrases_lower = [p.lower() for p in key_phrases]
    
    # Required topics for underwriting
    required_topics = {
        "line of business": ["line of business", "coverage", "lob", "property", "casualty", "health"],
        "coverage limits": ["limits", "limit", "limit of liability", "lol"],
        "loss history": ["loss", "claims", "loss history", "prior claims", "claims experience"],
        "renewal date": ["renewal", "effective date", "expiration", "term"],
        "premium": ["premium", "rate", "pricing", "cost"],
    }
    
    missing_info = []
    for topic, keywords in required_topics.items():
        if not any(kw in phrase for phrase in phrases_lower for kw in keywords):
            missing_info.append(f"{topic} not mentioned in email")
    
    return missing_info

# Output: ["loss history not mentioned in email"]
# NOT: ["Loss history/claims experience not provided"] (hardcoded)
```

---

### **5. Linked Entities (Knowledge Graph)**

**What Azure provides:**
```python
response = self.client.recognize_linked_entities(documents=[body_text])
result = response[0]

for entity in result.entities:
    print(f"Entity: {entity.name}")
    print(f"  Category: {entity.category}")
    print(f"  Wikipedia URL: {entity.url}")  # Links to knowledge graph
    print(f"  Confidence: {entity.confidence_score}")

# Output:
# Entity: Acme Manufacturing
#   Category: Company
#   Wikipedia URL: https://en.wikipedia.org/wiki/Acme_Manufacturing
#   Confidence: 0.89
```

**What we could do:**
```python
# Lookup company from knowledge graph to enhance context
# (Could fetch SIC code, industry, company size, etc.)
```

---

### **6. PII Detection**

**What Azure provides:**
```python
from azure.ai.textanalytics import PiiEntityCategory

response = self.client.recognize_pii_entities(
    documents=[body_text],
    categories_filter=[
        PiiEntityCategory.EMAIL,
        PiiEntityCategory.PHONE_NUMBER,
    ]
)
result = response[0]

for entity in result.entities:
    print(f"PII: {entity.text} (category: {entity.category}, confidence: {entity.confidence_score})")

# Output:
# PII: shreyas@acme.com (category: EMAIL, confidence: 0.99)
# PII: 555-123-4567 (category: PHONE_NUMBER, confidence: 0.95)
```

**We could use this for:**
```python
# Instead of generic NER extraction, use PII-specific detection
# Higher confidence for phone/email than generic NER
```

---

### **7. Language Detection**

**What Azure provides:**
```python
response = self.client.detect_language(documents=[body_text])
result = response[0]

print(result.primary_language.name)  # "English"
print(result.primary_language.iso6391_name)  # "en"
print(result.primary_language.confidence_score)  # 0.99

# Output:
# English
# en
# 0.99
```

**We could use this for:**
```python
# Handle multilingual broker emails
# Process emails in Spanish, French, etc.
if result.primary_language.iso6391_name != "en":
    # Translate or warn about language
```

---

### **8. Text Analytics for Health (Medical NER)**

**What Azure provides:**
```python
from azure.ai.textanalytics import AnalyzeHealthcareEntitiesAction

response = self.client.begin_analyze_healthcare_entities(documents=[body_text])
# Returns medical entities, relationships between them

# Note: Not relevant for insurance but shows SDK extensibility
```

---

### **9. Custom Text Classification (If We Train a Model)**

**What Azure provides:**
```python
response = self.client.begin_single_label_classify(
    documents=[body_text],
    model_name="my-explicit-vs-inferred-model"
)
result = response[0].classification

# Returns: class="explicit" or "inferred" with confidence
```

**We would need to:**
- Train the model first (requires labeled examples)
- Then use it for classification

---

## **How Much Do We Actually Use?**

| Azure Capability | Used? | Current Implementation |
|-----------------|-------|----------------------|
| Sentiment (document-level) | ✅ | Yes, we use it |
| Sentiment (sentence-level) | ❌ | Ignored, we only get document-level |
| Opinion mining | ❌ | Not used, we hardcode reasoning |
| Entity confidence scores | ❌ | Extracted but ignored |
| Key phrases | ❌ | Not used, hardcoded missing_info |
| Linked entities | ❌ | Not used |
| PII detection | ❌ | Not used |
| Language detection | ❌ | Not used |
| Custom classification | ❌ | Not trained |

---

## **What We SHOULD Be Doing (Revised Code)**

```python
def generate_briefing_using_sdk(self, broker_email: str, body_text: str, 
                                subject: str, sender_name: str = "Unknown",
                                sender_company: str = "Unknown") -> UnderwriterBriefing:
    """Generate briefing using full Azure SDK capabilities."""
    
    briefing = UnderwriterBriefing(...)
    
    # === Use Azure for EVERYTHING ===
    
    # 1. Sentiment with opinions
    sentiment_response = self.client.analyze_sentiment(
        documents=[body_text],
        language="en",
        include_opinion_mining=True
    )
    sentiment_result = sentiment_response[0]
    
    # Extract sentence-level analysis for better reasoning
    positive_sentences = [s for s in sentiment_result.sentences if s.sentiment == "positive"]
    opinions = {}
    for sentence in sentiment_result.sentences:
        for opinion in sentence.mined_opinions:
            opinions[opinion.target.text.lower()] = {
                "sentiment": sentence.sentiment,
                "confidence": opinion.target.confidence_score
            }
    
    # 2. Entities with confidence filtering
    entity_response = self.client.recognize_entities(documents=[body_text])
    entity_result = entity_response[0]
    high_conf_entities = {
        "people": [e for e in entity_result.entities 
                   if e.category == "PERSON" and e.confidence_score > 0.8],
        "organizations": [e for e in entity_result.entities 
                         if e.category == "ORGANIZATION" and e.confidence_score > 0.8],
    }
    
    # 3. Key phrases for missing info detection
    phrases_response = self.client.extract_key_phrases(documents=[body_text], language="en")
    key_phrases = phrases_response[0].key_phrases
    
    # 4. Build reasoning from actual SDK data
    if "collaboration" in opinions:
        reasoning = (
            f"Email expresses {opinions['collaboration']['sentiment']} sentiment "
            f"about collaboration (confidence: {opinions['collaboration']['confidence']:.0%}), "
            f"plus {len(positive_sentences)}/{len(sentiment_result.sentences)} positive sentences"
        )
    else:
        reasoning = f"Overall {len(positive_sentences)}/{len(sentiment_result.sentences)} sentences are positive"
    
    briefing.implied_goals.append(ExtractedFact(
        text="Build collaborative relationship",
        source=SourceType.INFERRED,
        confidence=0.80,
        reasoning=reasoning  # ← Dynamically generated from SDK data
    ))
    
    # 5. Detect missing info from actual key phrases
    missing_topics = {
        "line of business": not any(p in " ".join(key_phrases).lower() for p in ["line", "lob", "coverage"]),
        "loss history": not any(p in " ".join(key_phrases).lower() for p in ["loss", "claims", "history"]),
    }
    briefing.missing_info = [topic for topic, is_missing in missing_topics.items() if is_missing]
    
    return briefing
```

---

## **The Answer to Your Question**

**NO, this does NOT have to be hardcoded!**

The Azure SDK provides methods for:
- ✅ Sentence-level sentiment analysis
- ✅ Opinion mining (sentiment about specific topics)
- ✅ Entity confidence scores
- ✅ Key phrase extraction
- ✅ Linked entities
- ✅ PII detection
- ✅ Language detection
- ✅ Custom classification (with training)

**We're only using 2 out of 8+ capabilities**, and we're using them in a basic way (document-level only).

To do this properly, we should:
1. Use `include_opinion_mining=True` in sentiment analysis
2. Extract sentence-level sentiment, not just document-level
3. Use entity confidence scores from NER
4. Use key phrase extraction for missing info detection
5. Generate reasoning dynamically from SDK results instead of hardcoding templates

This would make the reasoning **actually derived from the content**, not just templated strings.

