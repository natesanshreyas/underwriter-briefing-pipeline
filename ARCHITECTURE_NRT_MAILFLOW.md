# Recommended NRT Mail Ingestion Architecture

## System View (aligned to your 1–4 flow)

```mermaid
flowchart LR
    subgraph STEP1[1) Mailbox Onboarding]
        IT[IT Creates Mailbox]
        TRG[Onboarding Trigger Event]
        LA[Logic App]
        SUBCREATE[Create Graph Subscription + Change Notification\nresource: /users/{mailboxId}/messages\nnotificationUrl: ingress HTTPS endpoint]
        IT --> TRG --> LA --> SUBCREATE
    end

    subgraph STEP2[2) Subscription Manager (Scheduled + Event-driven)]
        RECON[ACA Job (every 1-3 hours)]
        GUSERS[Graph: list mailbox IDs]
        GSUBS[Graph: list subscriptions]
        REG[(Registry DB\nmailboxId, subscriptionId, expiry, status)]
        DIFF[Find missing/expiring subscriptions\ncreate or renew (<24h to expiry)]
        RECON --> GUSERS
        RECON --> GSUBS
        GUSERS --> REG
        GSUBS --> REG
        REG --> DIFF --> RECON
    end

    subgraph STEP3[3) Runtime Notification]
        MBOX[Mailbox receives new email]
        GNOTIF[Graph Change Notification\nJSON payload with mailbox context]
        NIN[Notification Ingress\nHTTPS endpoint -> Service Bus publisher]
        MBOX --> GNOTIF --> NIN
    end

    subgraph STEP4[4) Queue + Ingestion]
        SB[(Azure Service Bus)]
        INGEST[ACA Ingestion Worker\nAutoscale]
        CATEG[Content understanding]
        DELTA[Graph Delta Query by mailboxId]
        TOKENS[(Delta checkpoint store)]
        NIN -->|enqueue| SB --> INGEST
        INGEST --> DELTA
        DELTA --> INGEST
        INGEST --> CATEG
        INGEST -->|external-only progression| TOKENS
    end

    SUBCREATE --> GNOTIF
    DIFF --> SUBCREATE
```

## Authentication model for 100+ mailboxes

- You do not use one secret per mailbox.
- The ingestion worker uses one app registration (client ID, tenant ID, client secret/cert) with app permissions.
- Queue message includes mailboxId (or subscriptionId mapped to mailboxId).
- Worker calls Graph for that mailboxId using the same app identity.
- This scales to hundreds of mailboxes because auth is app-scoped, while processing is mailbox-scoped.

## Key notes

- POST /subscriptions = create subscription.
- PATCH /subscriptions/{id} = renew before expiry.
- Subscription manager should run frequently (every 1-3 hours), plus onboarding-triggered creation.
- Graph sends notifications to an HTTPS endpoint; the ingress endpoint should immediately publish to Service Bus and return.

