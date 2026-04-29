#!/bin/bash
# =============================================================================
# deploy_aks.sh  —  Provisions Azure infrastructure and deploys the
#                   NRT mail ingestion pipeline to AKS.
#
# What this does:
#   1.  Create resource group (if missing)
#   2.  Create Azure Container Registry
#   3.  Build & push webhook + worker Docker images
#   4.  Create AKS cluster attached to ACR
#   5.  Create Event Grid Custom Topic
#   6.  Create Event Hubs namespace + hub
#   7.  Create Storage Account (delta token store)
#   8.  Apply Kubernetes manifests (namespace, config, secrets, deployments)
#   9.  Install nginx ingress controller
#   10. Wait for webhook LoadBalancer IP, then register Graph subscriptions
#   11. Create Event Grid subscription → worker endpoint
#
# Usage:
#   export GRAPH_TENANT_ID=...
#   export GRAPH_CLIENT_ID=...
#   export GRAPH_CLIENT_SECRET=...
#   export OPENAI_API_KEY=...
#   export MAILBOX_IDS="user1@domain.com user2@domain.com"
#   ./deploy_aks.sh
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — change these to match your environment
# ---------------------------------------------------------------------------
RG="${RG:-rg-shreyas-mailnrt-aks}"
REGION="${REGION:-eastus}"
ACR_NAME="${ACR_NAME:-acrshreyas$(openssl rand -hex 4)}"
AKS_CLUSTER="${AKS_CLUSTER:-aks-shreyas-mailnrt}"
EG_TOPIC="${EG_TOPIC:-eg-shreyas-mailnrt}"
EH_NAMESPACE="${EH_NAMESPACE:-ehn-shreyas-mailnrt-$(openssl rand -hex 3)}"
EH_HUB="${EH_HUB:-email-intents}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-stshreyasnrt$(openssl rand -hex 3)}"
GRAPH_CLIENT_STATE="${GRAPH_CLIENT_STATE:-shreyas-nrt-secret}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NRT_DIR="$SCRIPT_DIR/nrt_aks"
K8S_DIR="$SCRIPT_DIR/k8s"

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
for var in GRAPH_TENANT_ID GRAPH_CLIENT_ID GRAPH_CLIENT_SECRET OPENAI_API_KEY; do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: Required env var $var is not set."
    exit 1
  fi
done

echo ""
echo "================================================================="
echo " NRT Mail Ingestion Pipeline — AKS Deployment"
echo "================================================================="
echo " Resource Group : $RG"
echo " Region         : $REGION"
echo " ACR            : $ACR_NAME"
echo " AKS Cluster    : $AKS_CLUSTER"
echo " Event Grid     : $EG_TOPIC"
echo " Event Hubs NS  : $EH_NAMESPACE / $EH_HUB"
echo " Storage        : $STORAGE_ACCOUNT"
echo "================================================================="
echo ""

# ---------------------------------------------------------------------------
# 1. Resource Group
# ---------------------------------------------------------------------------
echo "[1/11] Resource group..."
az group create --name "$RG" --location "$REGION" --output none
echo "  OK: $RG"

# ---------------------------------------------------------------------------
# 2. Azure Container Registry
# ---------------------------------------------------------------------------
echo "[2/11] Container Registry..."
az acr create \
  --name "$ACR_NAME" \
  --resource-group "$RG" \
  --sku Basic \
  --admin-enabled true \
  --output none
echo "  OK: $ACR_NAME"

ACR_LOGIN_SERVER="$ACR_NAME.azurecr.io"
ACR_USERNAME=$(az acr credential show -n "$ACR_NAME" -g "$RG" --query username -o tsv)
ACR_PASSWORD=$(az acr credential show -n "$ACR_NAME" -g "$RG" --query "passwords[0].value" -o tsv)

# ---------------------------------------------------------------------------
# 3. Build & push Docker images
# ---------------------------------------------------------------------------
echo "[3/11] Building & pushing Docker images..."
az acr login --name "$ACR_NAME"

WEBHOOK_IMAGE="$ACR_LOGIN_SERVER/webhook-service:latest"
WORKER_IMAGE="$ACR_LOGIN_SERVER/email-ingestion-worker:latest"

docker build -f "$NRT_DIR/Dockerfile.webhook" -t "$WEBHOOK_IMAGE" "$NRT_DIR"
docker push "$WEBHOOK_IMAGE"
echo "  Pushed: $WEBHOOK_IMAGE"

docker build -f "$NRT_DIR/Dockerfile.worker" -t "$WORKER_IMAGE" "$NRT_DIR"
docker push "$WORKER_IMAGE"
echo "  Pushed: $WORKER_IMAGE"

# ---------------------------------------------------------------------------
# 4. AKS Cluster
# ---------------------------------------------------------------------------
echo "[4/11] AKS cluster (this takes ~5 minutes)..."
if ! az aks show -n "$AKS_CLUSTER" -g "$RG" &>/dev/null; then
  az aks create \
    --name "$AKS_CLUSTER" \
    --resource-group "$RG" \
    --node-count 2 \
    --node-vm-size Standard_B2s \
    --attach-acr "$ACR_NAME" \
    --enable-cluster-autoscaler \
    --min-count 1 \
    --max-count 5 \
    --generate-ssh-keys \
    --output none
  echo "  OK: Created $AKS_CLUSTER"
else
  echo "  OK: $AKS_CLUSTER already exists"
fi

az aks get-credentials --name "$AKS_CLUSTER" --resource-group "$RG" --overwrite-existing
echo "  kubectl context set to $AKS_CLUSTER"

# ---------------------------------------------------------------------------
# 5. Event Grid Custom Topic
# ---------------------------------------------------------------------------
echo "[5/11] Event Grid Custom Topic..."
az eventgrid topic create \
  --name "$EG_TOPIC" \
  --resource-group "$RG" \
  --location "$REGION" \
  --output none
EG_ENDPOINT=$(az eventgrid topic show -n "$EG_TOPIC" -g "$RG" --query endpoint -o tsv)
EG_KEY=$(az eventgrid topic key list -n "$EG_TOPIC" -g "$RG" --query key1 -o tsv)
echo "  OK: $EG_ENDPOINT"

# ---------------------------------------------------------------------------
# 6. Event Hubs
# ---------------------------------------------------------------------------
echo "[6/11] Event Hubs namespace + hub..."
az eventhubs namespace create \
  --name "$EH_NAMESPACE" \
  --resource-group "$RG" \
  --location "$REGION" \
  --sku Standard \
  --output none

az eventhubs eventhub create \
  --name "$EH_HUB" \
  --namespace-name "$EH_NAMESPACE" \
  --resource-group "$RG" \
  --partition-count 4 \
  --output none

EH_CONNECTION_STRING=$(az eventhubs namespace authorization-rule keys list \
  --namespace-name "$EH_NAMESPACE" \
  --resource-group "$RG" \
  --name RootManageSharedAccessKey \
  --query primaryConnectionString -o tsv)
echo "  OK: $EH_NAMESPACE/$EH_HUB"

# ---------------------------------------------------------------------------
# 7. Storage Account (delta tokens)
# ---------------------------------------------------------------------------
echo "[7/11] Storage account (delta tokens)..."
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RG" \
  --location "$REGION" \
  --sku Standard_LRS \
  --output none

STORAGE_CONNECTION_STRING=$(az storage account show-connection-string \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RG" \
  --query connectionString -o tsv)
echo "  OK: $STORAGE_ACCOUNT"

# ---------------------------------------------------------------------------
# 8. Apply Kubernetes manifests
# ---------------------------------------------------------------------------
echo "[8/11] Applying Kubernetes manifests..."

# Namespace
kubectl apply -f "$K8S_DIR/namespace.yaml"

# ConfigMap
kubectl apply -f "$K8S_DIR/configmap.yaml"

# Secrets (create/replace imperatively so we never store real values in YAML)
kubectl create secret generic mail-ingestion-secrets \
  --namespace mail-ingestion \
  --from-literal=GRAPH_TENANT_ID="$GRAPH_TENANT_ID" \
  --from-literal=GRAPH_CLIENT_ID="$GRAPH_CLIENT_ID" \
  --from-literal=GRAPH_CLIENT_SECRET="$GRAPH_CLIENT_SECRET" \
  --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY" \
  --from-literal=EVENT_GRID_TOPIC_ENDPOINT="$EG_ENDPOINT" \
  --from-literal=EVENT_GRID_TOPIC_KEY="$EG_KEY" \
  --from-literal=EVENTHUB_CONNECTION_STRING="$EH_CONNECTION_STRING" \
  --from-literal=STORAGE_CONNECTION_STRING="$STORAGE_CONNECTION_STRING" \
  --dry-run=client -o yaml | kubectl apply -f -

# Patch image references in deployment manifests and apply
sed "s|ACR_NAME.azurecr.io|$ACR_LOGIN_SERVER|g" "$K8S_DIR/webhook-deployment.yaml" \
  | kubectl apply -f -

sed "s|ACR_NAME.azurecr.io|$ACR_LOGIN_SERVER|g" "$K8S_DIR/worker-deployment.yaml" \
  | kubectl apply -f -

kubectl apply -f "$K8S_DIR/webhook-service.yaml"
kubectl apply -f "$K8S_DIR/worker-hpa.yaml"

echo "  OK: manifests applied"

# ---------------------------------------------------------------------------
# 9. nginx ingress controller (for worker's Event Grid push endpoint)
# ---------------------------------------------------------------------------
echo "[9/11] nginx ingress controller..."
if ! kubectl get ns ingress-nginx &>/dev/null; then
  kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.1/deploy/static/provider/cloud/deploy.yaml
  echo "  Waiting for ingress controller to become ready..."
  kubectl wait --namespace ingress-nginx \
    --for=condition=ready pod \
    --selector=app.kubernetes.io/component=controller \
    --timeout=180s
fi
echo "  OK: ingress-nginx ready"

# Retrieve ingress controller IP for the worker hostname
INGRESS_IP=$(kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
WORKER_HOSTNAME="${INGRESS_IP}.nip.io"
echo "  Worker hostname (nip.io): $WORKER_HOSTNAME"

# Apply worker ingress with resolved hostname
sed "s|WORKER_HOSTNAME|$WORKER_HOSTNAME|g" "$K8S_DIR/worker-ingress.yaml" \
  | kubectl apply -f -

# ---------------------------------------------------------------------------
# 10. Wait for webhook LoadBalancer IP
# ---------------------------------------------------------------------------
echo "[10/11] Waiting for webhook LoadBalancer IP..."
for i in $(seq 1 30); do
  WEBHOOK_IP=$(kubectl get svc -n mail-ingestion webhook-service \
    -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
  if [[ -n "$WEBHOOK_IP" ]]; then
    break
  fi
  echo "  ... still waiting ($i/30)"
  sleep 10
done
if [[ -z "$WEBHOOK_IP" ]]; then
  echo "ERROR: LoadBalancer IP not assigned after 5 minutes. Check AKS quota."
  exit 1
fi
WEBHOOK_URL="http://$WEBHOOK_IP/graph/notifications"
echo "  Webhook URL: $WEBHOOK_URL"

# Register Graph change notification subscription for each mailbox
if [[ -n "${MAILBOX_IDS:-}" ]]; then
  echo "  Registering Graph subscriptions for: $MAILBOX_IDS"
  GRAPH_TOKEN=$(curl -s -X POST \
    "https://login.microsoftonline.com/$GRAPH_TENANT_ID/oauth2/v2.0/token" \
    -d "client_id=$GRAPH_CLIENT_ID&client_secret=$GRAPH_CLIENT_SECRET&scope=https://graph.microsoft.com/.default&grant_type=client_credentials" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

  for MAILBOX in $MAILBOX_IDS; do
    EXPIRY=$(date -u -d '+3 days' '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
      || date -u -v+3d '+%Y-%m-%dT%H:%M:%SZ')
    curl -s -X POST "https://graph.microsoft.com/v1.0/subscriptions" \
      -H "Authorization: Bearer $GRAPH_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{
        \"changeType\": \"created,updated\",
        \"notificationUrl\": \"$WEBHOOK_URL\",
        \"resource\": \"users/$MAILBOX/messages\",
        \"expirationDateTime\": \"$EXPIRY\",
        \"clientState\": \"$GRAPH_CLIENT_STATE\"
      }" | python3 -m json.tool
    echo "  Subscribed: $MAILBOX"
  done
fi

# ---------------------------------------------------------------------------
# 11. Event Grid subscription → worker
# ---------------------------------------------------------------------------
echo "[11/11] Event Grid subscription → worker..."
WORKER_EG_URL="https://$WORKER_HOSTNAME/eventgrid/events"
az eventgrid event-subscription create \
  --name "sub-mail-worker" \
  --source-resource-id "$(az eventgrid topic show -n "$EG_TOPIC" -g "$RG" --query id -o tsv)" \
  --endpoint "$WORKER_EG_URL" \
  --endpoint-type webhook \
  --event-delivery-schema EventGridSchema \
  --included-event-types "Microsoft.Graph.MailboxChanged" \
  --output none
echo "  OK: Event Grid → $WORKER_EG_URL"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "================================================================="
echo " Deployment complete!"
echo "================================================================="
echo " Webhook URL    : $WEBHOOK_URL"
echo " Worker host    : https://$WORKER_HOSTNAME/eventgrid/events"
echo " Event Grid     : $EG_ENDPOINT"
echo " Event Hub      : $EH_NAMESPACE/$EH_HUB"
echo " AKS cluster    : $AKS_CLUSTER"
echo "================================================================="
echo ""
echo "Monitor pods:"
echo "  kubectl get pods -n mail-ingestion"
echo ""
echo "Stream worker logs:"
echo "  kubectl logs -n mail-ingestion -l app=email-ingestion-worker -f"
echo ""
echo "Read from Event Hubs (CLI preview):"
echo "  az eventhubs eventhub consumer-group create -g $RG --namespace-name $EH_NAMESPACE --eventhub-name $EH_HUB --name preview"
echo ""
