# Support-Ticket Triage Agent

hiiii (◕‿◕) 

This is one of my fun, hands-on-learning-projects, built to actually *do* the things I previously talk about like: RAG, agent frameworks, and real cloud deployment, JUST FOR FUN.

It's an agentic support-ticket triage system: classify → RAG retrieve → tool-call → escalation
routing. Not tied to any single company's product, just a good excuse to get my hands dirty.

**Status: complete and functional** — RAG retrieval, LangGraph agent, evaluation harness, local Docker Compose
stack, and Azure Container Instances deployment all built, run, and verified end to end.

For the full story of how the Azure deployment actually got working (five distinct real failures,
root-caused one at a time), see **[AZURE_DEPLOYMENT.md](AZURE_DEPLOYMENT.md)**.

For the full build log — why each piece exists, what was learned, and the running list of
honest simplifications — see **[LEARNING_GUIDE.md](LEARNING_GUIDE.md)**.


* note that, it requires openai API KEY (see env.example) AND Azure account =). Altho just to test this, would cost you a couple of cents(if any)

## Architecture

```
  ticket text
      |
      v
 [1. CLASSIFY]  -->  ticket category + confidence (structured output, Pydantic schema)
      |
      v
 [2. RETRIEVE]  -->  top-k relevant KB chunks (RAG: OpenAI embeddings + Chroma)
      |
      v
 [3. TOOL-CALL] -->  mocked account-status lookup (billing/account_access tickets only)
      |
      v
 [4. DECIDE]    -->  auto_answer vs. escalate, with a stored reason
      |
      v
 [5. ANSWER / ESCALATE]
```

1. **Knowledge base** (`data/kb/`) — 16 short docs across 5 categories (billing, account_access,
   technical, security, escalation_policy) for a fictional SaaS product.
2. **RAG retrieval** (`src/ingest.py`, `src/retrieval.py`) — embeddings via OpenAI
   `text-embedding-3-small`, stored/queried in a local **Chroma** vector DB (Docker), cosine
   similarity.
3. **Agent orchestration** (`src/agent.py`, `src/tools.py`) — built with **LangGraph**: classify
   node, retrieve node, tool-call node, a decision node that computes escalation and *why*, and
   answer/escalate terminal nodes.
4. **Evaluation harness** (`src/eval.py`) — classification accuracy/precision/F1 (`sklearn`) +
   retrieval quality (recall@k, MRR) against a 20-ticket labeled test set.
5. **Demo UI** (`app.py`) — Gradio interface showing the full agent trace: classification, tool
   result, decision + reason, and final response — not just the final answer.
6. **Deployment** — Dockerized (multi-container: app + Chroma), deployed to Azure Container
   Instances and demoed live.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Orchestration | LangGraph | real agent framework, not custom orchestration |
| Embeddings | OpenAI `text-embedding-3-small` | cheap, good enough quality for this scope |
| Vector store | Chroma (local, Docker), cosine similarity | free, self-hosted; cosine is the standard metric for text embeddings |
| Structured output | Pydantic + `with_structured_output()` | validated classifier output, not a parsed string |
| Demo UI | Gradio | fast to stand up, clickable in an interview |
| Containerization | Docker + Docker Compose | multi-container (app + Chroma) locally, same images reused for cloud deploy |
| Deployment | Azure Container Instances | existing production experience to build on |
| Container registry | Azure Container Registry (Basic) | private registry for the built image |

## Project layout

```
support_triage_agent/
├── data/
│   ├── kb/                # 16-doc knowledge base for RAG
│   └── eval/               # test_tickets.json — labeled eval set
├── src/
│   ├── db.py               # shared Chroma connection + collection settings
│   ├── ingest.py           # chunk + embed + load into Chroma (--reset to rebuild)
│   ├── retrieval.py        # query Chroma for relevant chunks
│   ├── tools.py             # mocked tool functions (account-status lookup)
│   ├── agent.py             # LangGraph graph definition
│   └── eval.py               # evaluation harness (classification + retrieval metrics)
├── docker/
│   ├── Dockerfile                          # app container image
│   ├── entrypoint.sh                       # wait-for-Chroma -> seed KB -> start app
│   ├── docker-compose.yml                  # local stack: chroma + app
│   ├── aci-container-group.template.yaml   # Azure Container Instances deploy spec
│   ├── deploy_azure.sh                     # builds, pushes, deploys to Azure (real cost — you run it)
│   └── teardown_azure.sh                   # deletes everything deploy created
├── app.py                  # Gradio demo UI entrypoint
├── requirements.txt
└── .env.example
```

Code is formatted with [black](https://github.com/psf/black) (`black --line-length 100`).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # fill in OPENAI_API_KEY
docker compose -f docker/docker-compose.yml up -d   # starts local Chroma
python src/ingest.py --reset       # first run only: builds the collection under cosine similarity
```

## Running it

**Individual pieces, locally:**
```bash
python src/retrieval.py "I was charged twice this month, can I get a refund?"
python src/agent.py "I was charged twice this month, can I get a refund?"
python src/eval.py
```

**Full stack, containerized, locally** (proves the same setup that goes to Azure works end to end):
```bash
docker compose -f docker/docker-compose.yml up --build
# open http://localhost:7860
```

**Deployed to Azure** (real cost while running — see [AZURE_DEPLOYMENT.md](AZURE_DEPLOYMENT.md)
for the full walkthrough and the debugging story):
```bash
bash docker/deploy_azure.sh      # you run this — prints a live URL when done
# ... demo it ...
bash docker/teardown_azure.sh <resource-group-name>   # deletes everything, stops billing
# precisley: bash docker/teardown_azure.sh triage-agent-rg
```

## Evaluation

Run 2026-09-07, on `gpt-4o-mini`, 20-ticket labeled eval set, Chroma under cosine similarity.

| Metric | Score |
|---|---|
| Classification accuracy | 90% |
| Classification macro-F1 | 0.91 |
| Retrieval recall@3 | 100% |
| Retrieval MRR | 1.000 |

Per-category classification: `billing` F1=0.91, `technical` F1=0.89, `account_access` F1=0.75,
`security`/`other` F1=1.00. The 2 misclassifications (2/20) were both genuinely ambiguous
ground-truth calls, not clear model errors — e.g. a ticket asking to add a teammate *and* how it
affects billing, labeled `account_access`, predicted `billing`; a reasonable label either way.

**Caveat on the retrieval score, stated deliberately rather than left implicit:** a perfect
100%/1.000 is a flag to scrutinize, not just report. The same author (me, working with Claude)
wrote both the KB documents and the eval tickets in one sitting, so eval tickets likely echo their
matching KB doc's phrasing more closely than a real customer's ticket would — a classic eval-set
bias risk when test cases and system-under-test share an author. This measures the retrieval
*mechanism* works correctly; it's weaker evidence about performance on phrasing nobody designed.

## Known simplifications & design decisions

Honest trade-offs made to keep this project scoped, not oversights discovered later:

- **Chunking** is fixed-character-window (not semantic/paragraph-based) — fine at this KB's size,
  would need revisiting for longer real documents.
- **Ingestion upsert doesn't delete** stale chunks if a KB doc is removed or shrinks.
- **Tool-call trigger is hardcoded** by ticket category, not decided dynamically by the model via
  function-calling — a deliberate simplification over a fully agentic tool-use pattern.
- **Classifier categories and KB document categories are intentionally different taxonomies**
  (the classifier has no `escalation_policy` output — that's a document category, not a ticket
  type) — caught and fixed while building the evaluation set.
- **ACR admin credentials** (username/password) are used for the registry, not a managed identity —
  simplest path for a demo deployment; a production setup would use `az acr login` with
  Azure AD / managed identity instead.
- **No CI/CD** — the deploy script is run manually. A real production version would wire this into
  a pipeline (e.g. GitHub Actions) that builds, tests, and deploys on push.



Cheeeeers! 


Bahar ¯\\_(ツ)\_/¯