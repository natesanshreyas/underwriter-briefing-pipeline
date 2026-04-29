# Deployed NRT Mail Ingestion POC (Azure)

Date: 2026-02-21
Subscription: `Azure subscription 1`
Region: `eastus`

## Resources created

- Resource Group: `rg-shreyas-mailnrt-poc`
- Log Analytics: `log-shreyas-mailnrt-0221212141`
- Service Bus Namespace: `sb-shreyas-mailnrt-0221212141`
- Service Bus Queues:
  - `ingest-shard-0` ... `ingest-shard-7`
  - `ingest-deadletter`
- Storage Account: `stshreyasmail0221212141`
- ACA Environment: `acae-shreyas-mailnrt-0221212141`
- ACA Webhook App (external): `aca-webhook-shreyas-0221212141`
  - URL: `https://aca-webhook-shreyas-0221212141.wittycoast-8279cbed.eastus.azurecontainerapps.io/`
- ACA Worker App (internal): `aca-worker-shreyas-0221212141`
  - Scale: min `1`, max `10`
- ACA Reconciliation Job (hourly): `job-recon-shreyas-2212141`
  - Cron: `0 * * * *`
- Live Webhook App (real code): `webhook-live-shreyas2`
   - URL: `https://webhook-live-shreyas2.wittycoast-8279cbed.eastus.azurecontainerapps.io/`
- Live Worker App (real code): `worker-live-shreyas2`
   - Internal URL: `https://worker-live-shreyas2.internal.wittycoast-8279cbed.eastus.azurecontainerapps.io/`
- Auto-created ACR (for source deployments): `cac2a48f64dcacr`
- Graph App Registration (created): `app-graph-mailnrt-live-0221`
   - App ID: `a20f089b-d214-4d85-89fe-604a5214e06c`

## What this gives you now

- Live cloud footprint matching your recommended architecture shape
- Sharded queue topology for high-mailbox ingestion
- Separate webhook + worker compute layers in ACA
- Scheduled reconciliation job container in ACA Jobs
- Real webhook handler deployed and receiving notifications
- Real worker service deployed and consuming shard queues

## Remaining to make this fully functional for Graph inbox ingest

1. Confirm Graph admin consent in tenant for app `a20f089b-d214-4d85-89fe-604a5214e06c`.
2. Create mailbox subscriptions (`POST /subscriptions`) pointing to:
   - `https://webhook-live-shreyas2.wittycoast-8279cbed.eastus.azurecontainerapps.io/graph/notifications`
3. Replace worker placeholder ingestion block with full delta/query/classification logic.
4. Add queue-based scale rules to worker app
   - Scale on queue depth/lag
5. Add subscription registry + delta token DB table(s)
   - mailboxId, subscriptionId, expirationDateTime, status, lastCheckedAt, lastError, deltaToken

## Live test you can run now

```bash
curl -sS -X POST \
   https://webhook-live-shreyas2.wittycoast-8279cbed.eastus.azurecontainerapps.io/graph/notifications \
   -H 'Content-Type: application/json' \
   -d '{"value":[{"subscriptionId":"sub-demo-001","resource":"/users/mailbox-x/messages","tenantId":"tenant-demo","changeType":"created","clientState":"demo"}]}'
```

Expected response:

```json
{"received": 1, "enqueued": 1}
```

## Suggested next deployment step

Wire Graph subscription automation + mailbox delta logic into the now-deployed live services.
