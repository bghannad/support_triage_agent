#!/bin/bash
# Deletes everything deploy_azure.sh created, stopping all associated Azure
# billing. Safe to run any time after a demo — nothing local is affected.
#
#
# COST WARNING, read before running: ACI bills by the second while running —
# roughly 1.5 vCPU + 2.5GB total across both containers costs approximately
# $1.50-2.00/day if left running continuously. This is meant to be run right
# before you need a live demo, then torn down with teardown_azure.sh
# immediately after — NOT left running.
#
# Usage:
#   bash docker/teardown_azure.sh <resource-group-name>
# (deploy_azure.sh prints the exact command with the name filled in)

set -e

RESOURCE_GROUP="${1:?Usage: bash docker/teardown_azure.sh <resource-group-name>}"

echo "Deleting resource group '$RESOURCE_GROUP' and everything in it (registry, container group)..."
az group delete --name "$RESOURCE_GROUP" --yes --no-wait
echo "Deletion started (--no-wait: runs in the background). Confirm it's gone with:"
echo "  az group show --name $RESOURCE_GROUP"
echo "(should return a 'not found' error once deletion completes, usually within a few minutes)"
