#!/bin/bash
#
# Deployment script for Underwriter Briefing Agent + Batch Pipeline
# 
# This script:
# 1. Builds Docker images for agent UI and batch job
# 2. Pushes to Azure Container Registry (ACR)
# 3. Deploys agent to ACA Apps (long-running)
# 4. Deploys batch job to ACA Jobs (scheduled 2x daily)
#
# Prerequisites:
#   - Azure CLI installed and authenticated (az login)
#   - Docker installed and running
#   - az containerapp extension: az extension add -n containerapp
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh
#

set -e

# Configuration
PROJECT_NAME="underwriter-briefing"
RESOURCE_GROUP="your-resource-group"  # TODO: Update this
ACR_NAME="your-acr-name"               # TODO: Update this (e.g., shreyas123)
LOCATION="eastus"

AGENT_IMAGE="$ACR_NAME.azurecr.io/$PROJECT_NAME-agent:latest"
BATCH_IMAGE="$ACR_NAME.azurecr.io/$PROJECT_NAME-batch:latest"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}Underwriter Briefing Deployment${NC}"
echo -e "${BLUE}================================${NC}\n"

# 1. BUILD DOCKER IMAGES
echo -e "${BLUE}Step 1: Building Docker images...${NC}"

echo "  Building agent image..."
docker build -f Dockerfile.agent -t "$AGENT_IMAGE" . --no-cache
echo -e "${GREEN}  ✅ Agent image built${NC}"

echo "  Building batch job image..."
docker build -f Dockerfile.batch -t "$BATCH_IMAGE" . --no-cache
echo -e "${GREEN}  ✅ Batch job image built${NC}\n"

# 2. PUSH TO ACR
echo -e "${BLUE}Step 2: Pushing images to ACR...${NC}"

echo "  Logging in to ACR..."
az acr login --name "$ACR_NAME"

echo "  Pushing agent image..."
docker push "$AGENT_IMAGE"
echo -e "${GREEN}  ✅ Agent image pushed${NC}"

echo "  Pushing batch image..."
docker push "$BATCH_IMAGE"
echo -e "${GREEN}  ✅ Batch image pushed${NC}\n"

# 3. DEPLOY AGENT TO ACA APPS (Long-running)
echo -e "${BLUE}Step 3: Deploying Agent to ACA Apps...${NC}"

az containerapp create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PROJECT_NAME-agent" \
  --image "$AGENT_IMAGE" \
  --cpu 0.5 \
  --memory 1 \
  --ingress external \
  --target-port 8080 \
  --registry-server "$ACR_NAME.azurecr.io" \
  --registry-username "$ACR_NAME" \
  --registry-password "$(az acr credential show -n $ACR_NAME -o tsv --query passwords[0].value)" \
  --env-vars \
    AZURE_FUNCTIONS_BASE_URL="https://underwriter-briefing-api.azurewebsites.net/api" \
    OPENAI_API_KEY="@secrets/openai-key" \
    OPENAI_ENDPOINT="@secrets/openai-endpoint" \
    OPENAI_MODEL="gpt-4o-mini" \
  --secrets \
    openai-key="$OPENAI_API_KEY" \
    openai-endpoint="$OPENAI_ENDPOINT" \
  2>/dev/null || {
    # If create fails, try update
    az containerapp update \
      --resource-group "$RESOURCE_GROUP" \
      --name "$PROJECT_NAME-agent" \
      --image "$AGENT_IMAGE"
  }

echo -e "${GREEN}✅ Agent deployed to ACA Apps${NC}\n"

# Get the agent URL
AGENT_URL=$(az containerapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PROJECT_NAME-agent" \
  --query "properties.configuration.ingress.fqdn" -o tsv)

echo -e "${GREEN}🌐 Agent URL: https://$AGENT_URL${NC}\n"

# 4. DEPLOY BATCH JOB TO ACA JOBS (Scheduled)
echo -e "${BLUE}Step 4: Deploying Batch Job to ACA Jobs...${NC}"

az containerapp job create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PROJECT_NAME-batch" \
  --image "$BATCH_IMAGE" \
  --trigger-type schedule \
  --cron-expression "0 9 * * *" \
  --parallelism 1 \
  --replica-completion-count 1 \
  --cpu 1 \
  --memory 2 \
  --registry-server "$ACR_NAME.azurecr.io" \
  --registry-username "$ACR_NAME" \
  --registry-password "$(az acr credential show -n $ACR_NAME -o tsv --query passwords[0].value)" \
  --env-vars \
    OUTLOOK_MAIL_FOLDER="INBOX" \
    OUTLOOK_BATCH_SIZE="10" \
    LANGUAGE_ENDPOINT="@secrets/language-endpoint" \
    LANGUAGE_KEY="@secrets/language-key" \
    OPENAI_API_KEY="@secrets/openai-key" \
    OPENAI_ENDPOINT="@secrets/openai-endpoint" \
    COSMOS_ENDPOINT="@secrets/cosmos-endpoint" \
    COSMOS_KEY="@secrets/cosmos-key" \
    GRAPH_TENANT_ID="@secrets/graph-tenant-id" \
    GRAPH_CLIENT_ID="@secrets/graph-client-id" \
    GRAPH_CLIENT_SECRET="@secrets/graph-client-secret" \
  --secrets \
    language-endpoint="$LANGUAGE_ENDPOINT" \
    language-key="$LANGUAGE_KEY" \
    openai-key="$OPENAI_API_KEY" \
    openai-endpoint="$OPENAI_ENDPOINT" \
    cosmos-endpoint="$COSMOS_ENDPOINT" \
    cosmos-key="$COSMOS_KEY" \
    graph-tenant-id="$GRAPH_TENANT_ID" \
    graph-client-id="$GRAPH_CLIENT_ID" \
    graph-client-secret="$GRAPH_CLIENT_SECRET" \
  2>/dev/null || {
    # If create fails, try update
    az containerapp job update \
      --resource-group "$RESOURCE_GROUP" \
      --name "$PROJECT_NAME-batch" \
      --image "$BATCH_IMAGE"
  }

echo -e "${GREEN}✅ Batch job deployed to ACA Jobs (scheduled 9am daily)${NC}\n"

# Summary
echo -e "${BLUE}================================${NC}"
echo -e "${GREEN}DEPLOYMENT COMPLETE!${NC}"
echo -e "${BLUE}================================${NC}"
echo ""
echo "Agent Frontend:"
echo -e "  ${GREEN}https://$AGENT_URL${NC}"
echo ""
echo "Batch Job:"
echo -e "  ${GREEN}Scheduled: Daily at 9 AM UTC${NC}"
echo -e "  ${GREEN}Resource: $PROJECT_NAME-batch${NC}"
echo ""
echo "Next steps:"
echo "  1. Update environment variables for Graph API credentials"
echo "  2. Test agent at https://$AGENT_URL"
echo "  3. Monitor batch job logs: az containerapp job logs --follow"
echo ""
