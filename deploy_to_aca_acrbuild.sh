#!/bin/bash
#
# Deploy Underwriter Briefing System to Azure Container Apps
# Uses ACR Build (no local Docker needed)
#

set -e

# Configuration
RESOURCE_GROUP="lab-"
ACR_NAME="acrtibke7spoognw"
LOCATION="eastus"
ACA_ENV_NAME="underwriter-env"
AGENT_APP_NAME="underwriter-agent"
BATCH_JOB_NAME="underwriter-batch-job"

AGENT_IMAGE="$ACR_NAME.azurecr.io/underwriter-agent:latest"
BATCH_IMAGE="$ACR_NAME.azurecr.io/underwriter-batch:latest"

echo "🚀 Deploying Underwriter Briefing System to Azure Container Apps"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Step 1: Build and push images using ACR Build (no local Docker needed)
echo "🔨 Building images in ACR (this may take a few minutes)..."
echo "  Building agent image..."
az acr build \
    --registry "$ACR_NAME" \
    --image "underwriter-agent:latest" \
    --file Dockerfile.agent \
    .
echo "  ✅ Agent image built"

echo "  Building batch job image..."
az acr build \
    --registry "$ACR_NAME" \
    --image "underwriter-batch:latest" \
    --file Dockerfile.batch \
    .
echo "  ✅ Batch image built"

# Step 2: Create ACA environment if it doesn't exist
echo ""
echo "🌍 Setting up Container Apps environment..."
if ! az containerapp env show -n "$ACA_ENV_NAME" -g "$RESOURCE_GROUP" &>/dev/null; then
    echo "  Creating new environment: $ACA_ENV_NAME"
    az containerapp env create \
        --name "$ACA_ENV_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION"
    echo "  ✅ Environment created"
else
    echo "  ✅ Environment already exists"
fi

# Step 3: Get ACR credentials
echo ""
echo "🔐 Retrieving ACR credentials..."
ACR_USERNAME=$(az acr credential show -n "$ACR_NAME" --query username -o tsv)
ACR_PASSWORD=$(az acr credential show -n "$ACR_NAME" --query "passwords[0].value" -o tsv)

# Step 4: Deploy agent (Container App)
echo ""
echo "🤖 Deploying agent (Container App - always running)..."

# Load secrets from secrets.json
CLIENT_ID=$(jq -r '.CLIENT_ID' secrets.json)
LANGUAGE_ENDPOINT=$(jq -r '.LANGUAGE_ENDPOINT' secrets.json)
LANGUAGE_KEY=$(jq -r '.LANGUAGE_KEY' secrets.json)
OPENAI_API_KEY=$(jq -r '.OPENAI_API_KEY' secrets.json)
OPENAI_ENDPOINT=$(jq -r '.OPENAI_ENDPOINT' secrets.json)
OPENAI_MODEL=$(jq -r '.OPENAI_MODEL' secrets.json)
COSMOS_ENDPOINT=$(jq -r '.COSMOS_ENDPOINT' secrets.json)
COSMOS_KEY=$(jq -r '.COSMOS_KEY' secrets.json)

if az containerapp show -n "$AGENT_APP_NAME" -g "$RESOURCE_GROUP" &>/dev/null; then
    echo "  Updating existing agent app..."
    az containerapp update \
        --name "$AGENT_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --image "$AGENT_IMAGE"
else
    echo "  Creating new agent app..."
    az containerapp create \
        --name "$AGENT_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --environment "$ACA_ENV_NAME" \
        --image "$AGENT_IMAGE" \
        --target-port 8080 \
        --ingress external \
        --registry-server "$ACR_NAME.azurecr.io" \
        --registry-username "$ACR_USERNAME" \
        --registry-password "$ACR_PASSWORD" \
        --cpu 0.5 \
        --memory 1Gi \
        --min-replicas 1 \
        --max-replicas 3 \
        --env-vars \
            "AZURE_FUNCTIONS_BASE_URL=https://underwriter-briefing-api.azurewebsites.net/api" \
            "OPENAI_API_KEY=$OPENAI_API_KEY" \
            "OPENAI_ENDPOINT=$OPENAI_ENDPOINT" \
            "OPENAI_MODEL=$OPENAI_MODEL"
fi

echo "  ✅ Agent deployed"

# Get agent URL
AGENT_URL=$(az containerapp show -n "$AGENT_APP_NAME" -g "$RESOURCE_GROUP" --query properties.configuration.ingress.fqdn -o tsv)
echo "  🌐 Agent URL: https://$AGENT_URL"

# Step 5: Deploy batch job (ACA Job)
echo ""
echo "⏰ Deploying batch job (ACA Job - scheduled cron)..."

if az containerapp job show -n "$BATCH_JOB_NAME" -g "$RESOURCE_GROUP" &>/dev/null; then
    echo "  Updating existing batch job..."
    az containerapp job update \
        --name "$BATCH_JOB_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --image "$BATCH_IMAGE"
else
    echo "  Creating new batch job..."
    az containerapp job create \
        --name "$BATCH_JOB_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --environment "$ACA_ENV_NAME" \
        --trigger-type "Schedule" \
        --cron-expression "0 */6 * * *" \
        --image "$BATCH_IMAGE" \
        --registry-server "$ACR_NAME.azurecr.io" \
        --registry-username "$ACR_USERNAME" \
        --registry-password "$ACR_PASSWORD" \
        --cpu 1.0 \
        --memory 2Gi \
        --replica-timeout 3600 \
        --replica-retry-limit 1 \
        --parallelism 1 \
        --replica-completion-count 1 \
        --env-vars \
            "CLIENT_ID=$CLIENT_ID" \
            "LANGUAGE_ENDPOINT=$LANGUAGE_ENDPOINT" \
            "LANGUAGE_KEY=$LANGUAGE_KEY" \
            "OPENAI_API_KEY=$OPENAI_API_KEY" \
            "OPENAI_ENDPOINT=$OPENAI_ENDPOINT" \
            "OPENAI_MODEL=$OPENAI_MODEL" \
            "COSMOS_ENDPOINT=$COSMOS_ENDPOINT" \
            "COSMOS_KEY=$COSMOS_KEY" \
            "REPORT_WINDOW_DAYS=90"
fi

echo "  ✅ Batch job deployed (runs every 6 hours)"

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Resources created:"
echo "  • Agent URL:    https://$AGENT_URL"
echo "  • Batch Job:    Runs every 6 hours (cron: 0 */6 * * *)"
echo "  • Environment:  $ACA_ENV_NAME"
echo ""
echo "🧪 Test the agent:"
echo "  curl https://$AGENT_URL"
echo ""
echo "🔍 Monitor batch job:"
echo "  az containerapp job execution list -n $BATCH_JOB_NAME -g $RESOURCE_GROUP -o table"
echo ""
echo "▶️  Trigger batch job manually:"
echo "  az containerapp job start -n $BATCH_JOB_NAME -g $RESOURCE_GROUP"
echo ""
