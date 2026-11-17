#!/bin/bash
# Deploys the Support-Ticket Triage Agent to Azure Container Instances.
#
# Prerequisites (one-time):
#   - Azure CLI installed (brew install azure-cli) and logged in (az login)
#   - .env in the project root with a real OPENAI_API_KEY
#
# Usage (from the project root):
#   bash docker/deploy_azure.sh

set -e

RESOURCE_GROUP="triage-agent-rg"
LOCATION="germanywestcentral"
ACR_NAME="triageagentacr$RANDOM"   # ACR names must be globally unique
DNS_LABEL="triage-agent-$RANDOM"    # public URL will include this

if ! command -v az &> /dev/null; then
  echo "Azure CLI not found. Install it first: brew install azure-cli"
  exit 1
fi

if [ ! -f .env ]; then
  echo ".env not found in the project root — copy .env.example and fill in OPENAI_API_KEY first."
  exit 1
fi

# Load OPENAI_API_KEY from .env without exposing other variables
OPENAI_API_KEY=$(grep -E '^OPENAI_API_KEY=' .env | cut -d '=' -f2-)
if [ -z "$OPENAI_API_KEY" ] || [[ "$OPENAI_API_KEY" == sk-... ]]; then
  echo "OPENAI_API_KEY in .env looks missing or still a placeholder."
  exit 1
fi

echo "Checking Azure login..."
az account show > /dev/null || { echo "Not logged in. Run 'az login' first."; exit 1; }

echo "Creating resource group '$RESOURCE_GROUP' in $LOCATION (no-op if it already exists)..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" -o none

echo "Creating container registry '$ACR_NAME' (Basic tier)..."
az acr create --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --sku Basic -o none

ACR_LOGIN_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)

echo "Building the app image locally (ACR Tasks cloud build is not permitted on this subscription)..."
docker build --platform linux/amd64 -t "$ACR_LOGIN_SERVER/support-triage-agent:latest" -f docker/Dockerfile .

echo "Logging in to ACR..."
az acr login --name "$ACR_NAME"

echo "Pushing image to ACR..."
docker push "$ACR_LOGIN_SERVER/support-triage-agent:latest"

echo "Enabling registry admin credentials so ACI can pull the image..."
az acr update --name "$ACR_NAME" --admin-enabled true -o none
ACR_USERNAME=$(az acr credential show --name "$ACR_NAME" --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)

echo "Waiting for registry credentials to propagate..."
sleep 30

echo "Rendering container group spec..."
TMP_YAML=$(mktemp)
export DNS_LABEL ACR_LOGIN_SERVER ACR_USERNAME ACR_PASSWORD OPENAI_API_KEY
envsubst < docker/aci-container-group.template.yaml > "$TMP_YAML"

echo "Deploying container group (retrying if credentials have not propagated yet)..."
DEPLOY_OK=false
for attempt in 1 2 3 4 5; do
  if az container create --resource-group "$RESOURCE_GROUP" --file "$TMP_YAML"; then
    DEPLOY_OK=true
    break
  fi
  echo "Attempt $attempt failed - deleting and retrying in 30s..."
  az container delete --resource-group "$RESOURCE_GROUP" --name support-triage-agent --yes -o none 2>/dev/null || true
  sleep 30
done

if [ "$DEPLOY_OK" = true ]; then
  rm -f "$TMP_YAML"
else
  echo ""
  echo "Deploy failed after 5 attempts. Rendered spec kept for debugging at: $TMP_YAML"
  echo "(it contains your real OPENAI_API_KEY and ACR password in plain text - delete it once done: rm $TMP_YAML)"
  exit 1
fi

FQDN=$(az container show --resource-group "$RESOURCE_GROUP" --name support-triage-agent --query ipAddress.fqdn -o tsv)
echo ""
echo "Deployed. Give it ~30-60s to seed the knowledge base, then open:"
echo "  http://$FQDN:7860"
echo ""
echo "IMPORTANT: run 'bash docker/teardown_azure.sh $RESOURCE_GROUP' when you're done demoing"
echo "to stop billing — this does not tear itself down automatically."
