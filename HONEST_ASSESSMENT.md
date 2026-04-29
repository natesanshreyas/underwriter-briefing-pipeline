# The Truth: How We Determine Explicit vs Inferred (And What We're NOT Doing)

## **The Current (Simple) Implementation**

### **EXPLICIT Facts**
Our definition: **"Keyword appears literally in the email"**

```python
def extract_key_urgency_signals(self, text: str) -> list[ExtractedFact]:
    urgency_patterns = [
        (r"\b(urgent|ASAP|immediate|by\s+\w+day|deadline|as soon as|this week|today|tomorrow)\b", "timeline"),
        (r"\b(expect|expiring|renewal|effective|binding|by end of)\b", "renewal_signal"),
    ]
    
    for pattern, category in urgency_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            facts.append(ExtractedFact(
                text=match.group(1),                    # ← The matched keyword itself
                category=category,
                source=SourceType.EXPLICIT,             # ← Hardcoded "explicit"
                confidence=0.95,                        # ← Fixed confidence (not from Azure)
                citation=self.find_quote(match.group(1), text),  # ← Find sentence containing it
            ))
```

**Translation:** IF keyword matches regex THEN it's explicit.

**Examples:**
- ✅ Email contains "urgent" → `source=EXPLICIT, confidence=0.95`
- ✅ Email contains "$500K" → `source=EXPLICIT, confidence=0.9`
- ✅ Email contains "renewal" → `source=EXPLICIT, confidence=0.95`

**The Problem:** This is just **pattern matching**, not true "explicitness" detection. We're confusing "keyword present" with "explicitly stated".

---

### **INFERRED Facts**
Our definition: **"Derived from sentiment classification"**

```python
if sentiment == "Positive":
    briefing.implied_goals.append(ExtractedFact(
        text="Build collaborative relationship",
        category="relationship_goal",
        source=SourceType.INFERRED,
        confidence=0.80,                           # ← Capped at 0.80
        reasoning="Positive sentiment + collaborative language suggests relationship-focused engagement"  # ← HARDCODED STRING
    ))
elif sentiment == "Negative":
    briefing.implied_goals.append(ExtractedFact(
        text="Resolve conflict or address concerns",
        category="issue_resolution",
        source=SourceType.INFERRED,
        confidence=0.75,
        reasoning="Negative sentiment detected; likely addressing specific concerns or pressure"  # ← HARDCODED STRING
    ))
```

**Translation:** IF sentiment=Positive THEN infer collaboration.

**The Problem:** The reasoning is **hardcoded templates**, not actually derived from the email content. We're not explaining *why* the email suggests collaboration beyond "because sentiment is positive".

---

## **What We're Actually NOT Using from Azure**

You're right to call this out. Here are Azure capabilities we should be using but aren't:

### **1. Sentence-Level Sentiment**
Azure returns not just document-level sentiment, but **per-sentence sentiment**.

**What we COULD do:**
```python
response = self.client.analyze_sentiment(documents=[sentence for sentence in sentences], language="en")

# Now we get:
# Sentence 1: "We're aligned on next steps" → Positive (0.95)
# Sentence 2: "The submission was well organized" → Positive (0.92)
# Sentence 3: "Looking forward to closing this" → Positive (0.88)

# BETTER REASONING:
reasoning = f"Positive sentiment found in {len(positive_sentences)} of {len(all_sentences)} sentences, indicating sustained positive tone"
```

**Currently:** We only get document-level sentiment (one score for whole email).

---

### **2. Opinion Mining (Aspect-Based Sentiment)**
Azure can extract sentiment *about specific entities*.

**What we COULD do:**
```python
# Extract: sentiment toward "timeline", "collaboration", "pricing", etc.
response = self.client.analyze_opinion_mining(documents=[body_text])

# Gets us:
# - Target: "timeline" → Sentiment: Negative
# - Target: "collaboration" → Sentiment: Positive
# - Target: "pricing" → Sentiment: Neutral

# BETTER REASONING:
if target == "collaboration" and sentiment == "Positive":
    reasoning = "Email expresses positive sentiment specifically about collaboration (e.g., 'thanks for collaboration')"
else:
    reasoning = "General document sentiment is positive"
```

**Currently:** We don't use opinion mining at all.

---

### **3. Entity Linking with Confidence**
Azure NER returns confidence scores per entity.

**What we COULD do:**
```python
response = self.client.recognize_entities(documents=[body_text])
result = response[0]

for ent in result.entities:
    if ent.confidence_score < 0.7:
        continue  # Skip uncertain entities
    
    # Now we know confidence of extraction
    reasoning = f"Extracted {ent.text} with {ent.confidence_score:.0%} confidence as {ent.category}"
```

**Currently:** We extract entities but ignore their confidence scores.

---

### **4. Key Phrase Extraction**
Azure can extract what the email is *actually about*.

**What we COULD do:**
```python
response = self.client.extract_key_phrases(documents=[body_text])
phrases = response[0].key_phrases

# Gets us: ["Acme Manufacturing renewal", "well organized submission", "updated indication", "collaboration"]

# COMPARE with missing_info checklist:
missing_info = []
required_topics = ["coverage limits", "renewal date", "loss history", "premium", "claims experience"]

for topic in required_topics:
    if topic not in phrases:
        missing_info.append(f"{topic} not mentioned")

# BETTER REASONING for missing info:
reasoning = f"Extracted key phrases: {phrases}. Missing from discussion: {missing_info}"
```

**Currently:** Missing info is hardcoded list, not derived from actual content.

---

### **5. Summarization (Extractive or Abstractive)**
Azure can auto-generate what the email is about.

**What we COULD do:**
```python
# Get summarization
response = self.client.analyze_abstractive_summarization(documents=[body_text])

summary = response[0].summaries[0].text
# Returns: "Acme Manufacturing renewal is proceeding well with aligned next steps."

# Use this to generate better reasoning:
reasoning = f"Based on email summary ('{summary}'), broker is suggesting collaborative engagement"
```

**Currently:** We don't use summarization.

---

### **6. Custom Classification Models**
We could train an Azure custom model to classify "explicit" vs "inferred".

**What we COULD do:**
```python
# Train model on labeled data:
# Email text + Label: "This is an explicit request for quote" (explicit)
# Email text + Label: "This suggests interest in our services" (inferred)

response = self.client.classify_documents(body_text, model_name="explicit-vs-inferred")
result = response[0]  # Explicit or Inferred with confidence

source = SourceType.EXPLICIT if result.class_name == "explicit" else SourceType.INFERRED
confidence = result.confidence_score
```

**Currently:** We don't train custom models at all.

---

## **The Honest Assessment**

### **Current Implementation: 🔴 Too Simple**

```
EXPLICIT = regex keyword match + fixed confidence
INFERRED = IF sentiment THEN hardcoded goal + templated reasoning

This is rule-based, not truly intelligent.
```

### **What a Better Implementation Would Look Like: 🟢 Sophisticated**

```
EXPLICIT = Keyword appears + Azure NER confidence > 0.8 + Sentence-level positive sentiment

INFERRED = 
  1. Extract key phrases relevant to insurance (renewal, quote, coverage, etc.)
  2. Use opinion mining to get sentiment ABOUT these topics
  3. Cross-reference with custom model trained on explicit vs inferred patterns
  4. Generate reasoning from: 
     - Which sentences are positive/negative
     - What entities they mention
     - How confident the entity extraction is
     - How this differs from document average
```

---

## **Example: How It SHOULD Work**

### **Email:**
```
"Hi Jordan, we've completed our review of Acme Manufacturing renewal. 
The submission was well organized. We're aligned on next steps and expect 
an updated indication ready shortly. Thanks for the collaboration."
```

### **Current (Simple) Implementation:**
```
sentiment = "Positive" (document-level)
explicit_goal = "renewal" (keyword found)
inferred_goal = "Build collaborative relationship" (hardcoded IF sentiment=Positive)
reasoning = "Positive sentiment + collaborative language suggests relationship-focused engagement" (TEMPLATE)
```

### **What It SHOULD Be:**

```
SENTENCE-LEVEL ANALYSIS:
- "we've completed our review" → Sentiment: Positive (0.92)
  └─ Target: "review" → Opinion: positive
  
- "submission was well organized" → Sentiment: Positive (0.95)
  └─ Target: "submission" → Opinion: positive

- "We're aligned on next steps" → Sentiment: Positive (0.94)
  └─ Target: "alignment" → Opinion: positive, "next steps" → Opinion: positive

- "expect updated indication ready shortly" → Sentiment: Neutral (0.88)
  └─ This is a FACT, not sentiment

- "Thanks for collaboration" → Sentiment: Positive (0.96)
  └─ Target: "collaboration" → Opinion: strongly positive

EXPLICIT FACTS:
- "renewal" (keyword in "Acme Manufacturing renewal") 
  └─ Azure NER Confidence: 0.91
  └─ Sentence sentiment: Positive
  └─ source=EXPLICIT, confidence=0.91

- "expect...indication ready shortly" (timeline keyword "shortly")
  └─ source=EXPLICIT, confidence=0.93

INFERRED FACTS:
- "Build collaborative relationship"
  └─ Reason 1: Positive sentiment in 4/5 sentences (0.95 avg)
  └─ Reason 2: Opinion mining found "collaboration" mentioned with strong positive sentiment (0.96)
  └─ Reason 3: Custom model returns: "This is inferred collaborative intent" (0.87 confidence)
  └─ Overall reasoning: "Multiple positive sentiment indicators (4/5 sentences, avg 0.95) with explicit mention of collaboration (0.96), plus model-based inference (0.87) suggests collaborative intent"
  └─ source=INFERRED, confidence=0.82 (average of indicators)

MISSING INFO:
- Extracted key phrases: ["renewal", "submission", "well organized", "alignment", "collaboration"]
- Missing from discussion: ["coverage limits", "loss history", "renewal date", "premium", "claims experience"]
- Reasoning: "Key phrases don't include required underwriting topics: coverage limits, loss history, renewal date, premium, or claims experience. These are critical gaps for proceeding."
```

---

## **How to Fix This**

To use Azure capabilities properly, we'd need to:

### **Option 1: Use More Azure APIs (Low effort, Medium improvement)**
```python
def generate_briefing_improved(self, ...):
    # 1. Get sentence-level sentiment
    sentences = self.extract_sentences(body_text)
    sentence_sentiments = self.analyze_sentence_sentiment(sentences)
    
    # 2. Get opinion mining
    opinions = self.analyze_opinion_mining(body_text)
    
    # 3. Get key phrases
    key_phrases = self.extract_key_phrases(body_text)
    
    # 4. Generate reasoning from these
    reasoning = self._generate_reasoning(
        sentence_sentiments=sentence_sentiments,
        opinions=opinions,
        key_phrases=key_phrases,
    )
    
    return reasoning
```

### **Option 2: Train Custom Model (High effort, High accuracy)**
```python
# Train model on labeled examples
# model expects: email_text → explicit or inferred

# Then use it:
result = self.client.classify_document(body_text, model_name="explicit-vs-inferred")
source = SourceType.EXPLICIT if result.confidence > 0.8 else SourceType.INFERRED
```

### **Option 3: Hybrid (Medium effort, Best results)**
- Use Azure APIs for feature extraction
- Use rules to combine features into reasoning
- Use custom model as tiebreaker when uncertain

---

## **Bottom Line**

You caught a real weakness: **We're saying "Azure does this" when really we're doing simple rule-based logic and hardcoding reasoning strings.**

The current implementation is:
- ✅ Fast
- ✅ Cheap
- ✅ Auditable
- ❌ Simplistic (not using Azure's full power)
- ❌ Reasoning is templated, not derived
- ❌ Explicit/inferred distinction is just keyword presence vs sentiment

To be enterprise-grade, we should either:
1. Use more of Azure's capabilities (sentence sentiment, opinion mining, key phrases)
2. Train a custom model for explicit vs inferred classification
3. Generate reasoning dynamically instead of using templates

Which direction interests you?

