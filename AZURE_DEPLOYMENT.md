# Azure Deployment: Intro, What We Built, How, and How It Actually Went

This is the companion doc to the README's "Deployment" section — the full story, not just the
final commands. It exists because the debugging chain to get this working is arguably more
interview-relevant than the deployment succeeding on the first try would have been: five distinct,
realistic failure modes on a fresh Azure subscription, each root-caused from the actual CLI error
rather than guessed at.

## 1. Intro to Azure — the concepts this project actually touches

A few Azure building blocks, explained at the level needed to follow the rest of this doc:

- **Subscription** — your account's billing boundary and permission scope. Everything you create
  lives inside one subscription. New/free subscriptions start with a reduced feature set compared
  to an established paid one (more on this below).
- **Resource group** — a logical folder for related resources (this project's are all inside
  `triage-agent-rg`). Deleting a resource group deletes everything inside it in one shot — the
  basis for `teardown_azure.sh`. Important quirk: **a resource group is pinned to a region at
  creation time and cannot be moved** — you have to delete and recreate it to change region.
- **Region** — the physical datacenter location resources run in (e.g. `westeurope`,
  `germanywestcentral`). Azure sometimes restricts *new resource creation* in a specific region for
  certain subscription types, independent of anything about your account being wrong.
- **Resource provider** — Azure organizes its services as namespaces (`Microsoft.ContainerRegistry`,
  `Microsoft.ContainerInstance`, etc.) that a subscription must be explicitly *registered* to use
  before first use. New subscriptions start registered for only a minimal default set.
- **Azure Container Registry (ACR)** — a private Docker registry hosted in Azure. This project uses
  the Basic tier (cheapest, no advanced networking features, ~$0.17/day while it exists).
- **Azure Container Instances (ACI)** — runs containers directly, billed per-second while a
  container is actually `Running`, no VM or orchestrator to manage. Supports **multi-container
  groups**: multiple containers that share one network namespace and one public IP — this is what
  lets the `app` container reach the `chroma` container at `localhost`, not a hostname.
- **ACR admin credentials** — the simplest way (username/password) to let something outside Azure's
  own identity system pull from a private registry. Simpler than the production-grade alternative
  (managed identity), and fine for a demo project — called out explicitly in the README's "Known
  simplifications" as a deliberate shortcut.

## 2. What we built

A 2-container Azure Container Instances group, deployed from the exact same Docker images used
locally:

```
Public IP (one DNS label, e.g. triage-agent-24978.germanywestcentral.azurecontainer.io)
│
├── container: chroma   (chromadb/chroma:latest, port 8000)
│                         same image as docker-compose.yml uses locally
│
└── container: app       (our built image, port 7860, exposed publicly)
                          entrypoint: wait for Chroma -> seed KB -> start Gradio
                          talks to Chroma at "localhost:8000" (shared network namespace —
                          different from docker-compose's "chroma:8000" hostname-based networking)
```

Deployed 2026-09-10, demoed live, torn down immediately after — nothing left running.

## 3. How we built it

Three files do the work:

- **`docker/aci-container-group.template.yaml`** — the container group spec, in the YAML format
  `az container create --file` expects. Contains placeholders (`${DNS_LABEL}`, `${ACR_LOGIN_SERVER}`,
  `${ACR_USERNAME}`, `${ACR_PASSWORD}`, `${OPENAI_API_KEY}`) so the file itself never contains real
  secrets and is safe to commit to git.
- **`docker/deploy_azure.sh`** — the actual deploy sequence:
  1. Create the resource group (no-op if it already exists).
  2. Create the Container Registry.
  3. Build the app image **locally** and `docker push` it to that registry (see §4 for why not a
     cloud build).
  4. Enable ACR admin credentials and fetch the username/password.
  5. Render the YAML template with real values via `envsubst` (reads `${VAR}` placeholders,
     substitutes from the shell environment) into a temp file — this is the secret-injection
     mechanism that keeps real credentials out of git.
  6. Deploy the container group from that rendered file, retrying with a delay if needed (see §4).
  7. Print the live URL.
- **`docker/teardown_azure.sh`** — one command, `az group delete`, removes everything the deploy
  created.

Run manually, by design — Claude never triggers this script itself, since it starts real Azure
billing the moment it runs.

## 4. How we got it to work — the actual debugging chain

Five real failures, in the order they happened, each on a fresh Azure subscription with no prior
Azure resources of any kind:

**1. Region capacity restriction.**
```
(RequestDisallowedByAzure) ... The selected region is currently not accepting new customers
```
`westeurope` was throttling new resource creation for this subscription type. Not an account
problem — Azure manages datacenter capacity by sometimes restricting new signups in specific
regions. Fix: switched the target region to `germanywestcentral` in both the deploy script and the
YAML template.

**2. Resource-group region immutability.**
```
(InvalidResourceGroupLocation) ... The Resource group already exists in location 'westeurope'
```
The first (failed) run had already created the resource group in `westeurope` before hitting error
#1's failure downstream. Since a resource group can't be moved after creation, the region fix alone
wasn't enough — the stale group had to be deleted (`az group delete`) before a retry could create it
fresh in the new region.

**3. Resource provider not registered.**
```
(MissingSubscriptionRegistration) The subscription is not registered to use namespace
'Microsoft.ContainerRegistry'
```
A fresh subscription simply hadn't been registered for the ACR (or, it turned out shortly after,
ACI) resource provider yet. Fix: `az provider register --namespace Microsoft.ContainerRegistry`
and the same for `Microsoft.ContainerInstance`, pre-emptively, since the deploy would need both.

**4. ACR Tasks (cloud build) disallowed on this subscription tier.**
```
(TasksOperationsNotAllowed) ACR Tasks requests for the registry ... are not permitted
```
The original script used `az acr build`, which builds the Docker image *inside Azure* using a
managed build service ("ACR Tasks"). Free/trial subscriptions are commonly blocked from this
specific feature (a common abuse vector for free compute). Fix: switched to building the image
**locally** and pushing it — `docker build --platform linux/amd64 ...` (the `--platform` flag
matters specifically because development happened on Apple Silicon, which defaults to arm64, while
ACI only runs x86_64 images) followed by `az acr login` and `docker push`.

**5. ACR admin-credential propagation delay.**
```
(InaccessibleImage) The image '...' in container group '...' is not accessible.
Please check the image and registry credential.
```
The trickiest one — this error persisted across multiple fixes (adding the missing
`imageRegistryCredentials` block to the YAML; quoting the values in case of special characters) that
turned out not to be the real problem. The actual cause: **enabling ACR admin credentials on a
freshly created registry and immediately trying to use them for a deploy can race ahead of Azure's
internal propagation** — the credentials are technically valid (confirmed independently: a manual
`docker login` with the exact same username/password succeeded) but not yet usable by ACI's pull
path at the moment of deploy. Fix: added a retry loop to `deploy_azure.sh` — up to 5 attempts,
deleting the failed container group and waiting 30s between each. It succeeded on the 3rd attempt,
roughly 60-90 seconds after the credentials were first enabled.

**One operational note, not a technical bug:** partway through this debugging, a rendered deploy
spec (kept locally for inspection after a failure) was pasted into chat with only the ACR password
redacted — the OpenAI API key in the same file was not, and got rotated immediately as a precaution.
Worth including here because "I noticed and rotated a leaked credential immediately" is a more
useful thing to be able to say in an interview than pretending it didn't happen.

### Why this sequence is worth keeping, not smoothing over

Every one of these is a *category* of real cloud deployment friction, not a one-off fluke: capacity
limits, resource immutability, provider registration, subscription-tier feature restrictions, and
eventual-consistency/propagation delays. Hitting all five on one small project and fixing each from
the actual error message — rather than a tutorial that never fails — is a more complete demonstration
of "hands-on Azure deployment experience" than a clean first-try deploy would have been.
