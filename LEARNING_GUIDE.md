# Support-Ticket Triage Agent — Project Roadmap & Learning Guide

This is the map I used while building this project: what each piece is, why it exists, and what I
needed to be able to explain and defend afterward. Kept as-is rather than cleaned up into a polished
retrospective, because the real value of a document like this is showing the actual process, not a
tidied-up version of it.

---

## 1. Why this project exists

Multiple technical interviews converged on the same diagnosis: I could talk about RAG, agents, and
cloud deployment, but my CV didn't yet show I'd actually *built* them — a recognizable gap between
having heard of things and having hands-on experience with them.

So instead of taking another course, I built one real project that forces me to actually touch the
three missing pieces:

| Gap | What it means | How this project closes it |
|---|---|---|
| RAG | No vector DB / embeddings / retrieval eval in any prior project | Real embedding + retrieval, built from scratch, and evaluated |
| Agent frameworks | Prior agent work was custom code, not a framework | LangGraph, a real framework, not custom orchestration |
| Cloud depth | Azure experience was real but underselling itself | Deployed end to end myself, and can narrate every step, including what went wrong |

Classical ML (a separately flagged gap — XGBoost vs. Random Forest, feature engineering, etc.) is
deliberately **out of scope** here — kept as a separate, lighter prep track instead of bloating
this project.

---

## 2. The finished picture — what a "Support-Ticket Triage Agent" actually is

Picture a support ticket coming in: *"I was charged twice this month, can I get a refund?"* The
finished system does this:

```
  ticket text
      |
      v
 [1. CLASSIFY]  -->  "this is a billing question" (+ a confidence score)
      |
      v
 [2. RETRIEVE]  -->  pulls the most relevant KB doc(s) (RAG)
      |
      v
 [3. TOOL-CALL] -->  optionally calls a mocked function, "look up account status"
      |
      v
 [4. DECIDE]    -->  compute auto_answer vs. escalate + WHY (security ticket? low
                      confidence? locked account?)
      |
      v
 [5. ANSWER or ESCALATE]  -->  branches based on the decision above
```

Each bracket is a **node** in a LangGraph graph — this is what makes it an *agent* rather than a
plain chatbot: it makes a sequence of decisions and can branch (escalate vs. answer), rather than
just producing one text completion.

---

## 3. What was actually built, in order

### 3.1 Accounts
- Created an **OpenAI account**, added $10 in credits (auto-reload **off**), generated an API key.
- Created a **personal Azure account** ($200 free credit, 30 days).
- These live in a `.env` file in the project folder — never committed to git (see `.env.example`
  for the template).

### 3.2 Project scaffold

```
support_triage_agent/
├── data/
│   ├── kb/                # 16-doc synthetic knowledge base (3.3)
│   └── eval/               # test_tickets.json, the labeled eval set (3.7)
├── src/
│   ├── db.py                # shared Chroma connection + collection settings
│   ├── ingest.py            # chunk + embed + load into Chroma
│   ├── retrieval.py         # query Chroma for relevant chunks
│   ├── tools.py               # mocked "check account status" tool
│   ├── agent.py               # the LangGraph graph itself
│   └── eval.py                 # classification + retrieval evaluation
├── docker/
│   ├── Dockerfile                          # app container image
│   ├── entrypoint.sh                       # wait-for-Chroma -> seed KB -> start app
│   ├── docker-compose.yml                  # local stack: chroma + app
│   ├── aci-container-group.template.yaml   # Azure deploy spec
│   ├── deploy_azure.sh                     # build, push, deploy to Azure
│   └── teardown_azure.sh                   # delete everything deploy created
├── app.py               # Gradio demo UI
├── requirements.txt
└── .env.example
```

Also installed **Docker Desktop** (never used it before this project) — lets a real database
(Chroma) run locally inside an isolated container. `docker compose -f docker/docker-compose.yml
up -d` starts it in the background; `down` stops it.

### 3.3 The knowledge base (`data/kb/*.md`)
16 short synthetic documents for a fictional SaaS product, covering 5 categories: **billing** (4),
**account_access** (4), **technical** (4), **security** (2), **escalation_policy** (2). Each has a
`# Category:` / `# Title:` header plus a short body — the "encyclopedia" RAG retrieves from.

### 3.4 RAG retrieval — done and verified working
- **`ingest.py`** — reads `data/kb/`, chunks each doc, embeds chunks via OpenAI
  `text-embedding-3-small`, stores vectors + text + metadata in **Chroma**.
- **`retrieval.py`** — embeds a new query the same way, asks Chroma for the closest stored
  vectors (**similarity search**), returns the top-k chunks.

Verified with a live query — correctly returned "Refund policy" as the #1 match for a refund
question.

### 3.5 The LangGraph agent — done and verified working
- **`tools.py`** — `check_account_status(ticket_text)`: a **mocked** tool (keyword-matching, not
  a real API) that returns deterministic fake account data (e.g. `"locked"`, `"past_due"`), used
  to demonstrate the agent calling a tool and using its result in a downstream decision.
- **`agent.py`** — the actual graph: `classify → retrieve → tool_call → decide → answer/escalate`.
  - `TicketState`: one `TypedDict` that flows through every node, accumulating fields.
  - `classify_node`: `ChatOpenAI` + `.with_structured_output(ClassificationResult)` — a Pydantic
    schema, so the model returns a validated category/confidence/reasoning object, not a string
    that has to be parsed and hoped it doesn't break.
  - `retrieve_node`: thin wrapper reusing `retrieval.py`'s `retrieve()` — no reimplementation.
  - `tool_call_node`: calls `tools.py`'s mock, but **only** for `billing`/`account_access`
    categories — this trigger is hardcoded, not decided by the LLM (see section 7).
  - `decide_node`: the actual escalation logic (security → always escalate; confidence < 0.6 →
    escalate; locked account → escalate; else → auto-answer) — written as a real node (not just
    an edge-selector) so the *reason* gets stored in state, not just used invisibly for routing.
  - `route_after_decision`: trivial edge-selector, just reads `state["decision"]`.
  - `answer_node` / `escalate_node`: draft a grounded reply from retrieved KB context, or format
    an escalation message with its reason.
  - `build_graph()`: wires all of the above into a compiled, runnable LangGraph.

### 3.6 Fixing the distance-metric gap + removing duplicated connection code
While building the eval harness (3.7), fixed a loose end flagged back in 3.4: Chroma's distance
metric had defaulted to **L2** (never a deliberate choice), when **cosine similarity** is the
standard for comparing text embeddings.

**What changed, precisely:**
- New file **`db.py`** — the Chroma connection + collection logic that used to be duplicated
  separately inside `ingest.py` and `retrieval.py` now lives in exactly one place, so the two
  files can never drift out of sync on settings like the distance metric. It sets
  `metadata={"hnsw:space": "cosine"}` when creating the collection.
- **`ingest.py`** — removed its own inline Chroma-connection code; now imports `get_collection`
  (and `reset_collection`) from `db.py`. Added one new flag: `python src/ingest.py --reset` wipes
  and rebuilds the collection first (only needed the one time the metric changes); plain
  `python src/ingest.py` keeps its normal upsert-in-place behavior, unchanged.
- **`retrieval.py`** — removed its own duplicate `get_collection()` function; now imports it from
  `db.py` instead. Nothing else in the file changed.

**Why a reset is required, not optional:** Chroma bakes the distance metric into the actual
structure of its search index (the HNSW graph) at collection-creation time — there is no "update
metric" operation. Switching metrics means: delete the collection, create a fresh one under the
new metric, re-run ingestion to refill it. `python src/ingest.py --reset` does exactly that.
**Result: one collection, one metric (cosine), fully replacing the old L2 one — not two parallel
KB copies, not two similarity systems running side by side.**

### 3.7 Evaluation harness — done, run 2026-09-07
- **`data/eval/test_tickets.json`** — 20 labeled test tickets (5 billing, 5 technical, 4
  account_access, 4 other, 2 security), each with a ground-truth `true_category` and, where
  applicable, an `expected_doc` (which KB source file retrieval should surface).
- **`eval.py`** measures two genuinely different things:
  - **Classification**: runs `classify_node` on every test ticket, compares predicted vs. true
    category, computes accuracy/precision/recall/F1 via `sklearn.metrics`.
  - **Retrieval**: runs `retrieve()` on every ticket with a known expected doc, computes
    **recall@k** (did the right doc appear anywhere in the top k?) and **MRR** — Mean Reciprocal
    Rank (rewards the right doc ranking *higher* within top-k, not just being present; two systems
    can tie on recall@k but differ on MRR).

**A real bug caught while building this eval set, worth remembering as an interview story:** the
KB's document categories (5, including `escalation_policy`) and the ticket classifier's output
categories (5, including `other` instead) are **different taxonomies** — `escalation_policy` is a
category of *document* (a policy doc about when to escalate), not something a ticket could ever
be classified as. Caught this because 3 test tickets had an impossible `true_category` that the
classifier could never produce. Fixed in the eval set (corrected to `"other"`), not in the
classifier — the classifier's taxonomy was the correct one all along.

**Results:**
- Classification: 90% accuracy (18/20). Per-category F1: billing 0.91, technical 0.89,
  account_access 0.75, security 1.00, other 1.00. Macro-avg F1 0.91, weighted-avg F1 0.90 (close
  because the 5 categories are fairly balanced, 2-5 tickets each).
- The 2 misclassifications were both genuinely ambiguous ground-truth calls made while writing the
  eval set (e.g. a "add a teammate, how does it affect our bill" ticket labeled account_access,
  predicted billing) — worth being able to say precisely that, not just "10% error rate," since
  it's a materially different and more honest story.
- Retrieval: recall@3 = 100%, MRR = 1.000 — every scored ticket's correct doc ranked #1.
  **Read this skeptically, not as a pure win**: I wrote both the KB docs and the eval tickets in
  the same sitting, so eval tickets likely mirror their matching doc's own phrasing more than a
  real customer's ticket would — classic eval-set bias when the same author builds the system and
  its test cases. Confirms the retrieval *mechanism* works; weaker evidence about phrasing nobody
  designed for it.

### 3.8 Containerization and Azure deployment — done, run 2026-09-10
Built a Gradio demo UI (`app.py`), a real multi-container Docker setup (app + Chroma), and deployed
to Azure Container Instances — tested live, demoed, then torn down.

The Azure deployment surfaced five distinct, real failures on a fresh subscription (region capacity
restriction, resource-group region immutability, resource-provider registration, a subscription-tier
restriction on cloud-hosted builds, and an ACR credential-propagation delay) — each root-caused from
the actual CLI error and fixed in turn. Full chronicle: **[AZURE_DEPLOYMENT.md](AZURE_DEPLOYMENT.md)**.

---

## 4. Status

Both remaining tasks from the original plan are done:

| # | Task | What it demonstrates |
|---|---|---|
| 7 | Containerize + deploy to Azure Container Instances | Real, hands-on cloud-deployment experience — including the debugging, not just a clean deploy |
| 8 | README + portfolio packaging | The artifact shown in interviews |

---

## 5. Concepts I should be able to explain and defend

The bar I held this project to: name the exact stack, explain why it was chosen over alternatives,
describe a real failure hit along the way, show what changed after evaluation, quantify metrics,
discuss trade-offs out loud, unprompted.

- **Embeddings** — what they are, why `text-embedding-3-small` (cost/quality trade-off).
- **Vector database** — what Chroma does that a normal database can't; why local/free Chroma over
  a managed option like Pinecone or Azure AI Search, for this project's scale.
- **Chunking strategy** — why chunk at all; the trade-off between chunk size and context loss;
  why this project's fixed-character chunking is a simplification (see section 7).
- **Similarity metrics & HNSW** — L2 vs. cosine, why cosine is standard for text embeddings, and
  why the metric is fixed at index-creation time (baked into the graph structure) rather than
  chosen per-query.
- **RAG vs. fine-tuning** — why retrieval is the right tool here (knowledge changes often).
- **Agent frameworks vs. custom orchestration** — what LangGraph's explicit state + conditional
  edges give you that hand-rolled if/else code doesn't.
- **Structured output** — why `.with_structured_output()` + a Pydantic schema beats asking an LLM
  to "return JSON" in a prompt and parsing the string.
- **Tool-calling** — how an LLM can decide to call a function; and the honest distinction that
  this project's tool-call trigger is hardcoded on category, not model-decided (section 7).
- **Docker / containers** — why containerize (reproducible environment, same thing runs locally
  and on Azure).
- **Evaluation metrics** — classification: accuracy/precision/F1. Retrieval: recall@k vs. MRR,
  and why they measure genuinely different things.
- **Azure Container Instances** — why ACI for a project this size vs. something heavier like AKS;
  the five real deployment failures and fixes (see `AZURE_DEPLOYMENT.md`).

---

## 6. How to use this document

Skim the relevant row in section 3 to see why a piece exists before reading the code. Try explaining
each piece out loud, as if to a technical interviewer. If that's hard for any piece, that's the
signal to slow down and re-derive it rather than move on.

---

## 7. Known simplifications & design decisions (the honest list)

Every deliberate shortcut or gap in the build, in one place — not scattered across notes. None of
these are secrets to hide; they're exactly the kind of trade-off worth naming out loud, unprompted,
before an interviewer finds it first.

1. **Chunking is crude** (`ingest.py`) — fixed 800-character windows with 100-character overlap,
   not paragraph/semantic boundaries. Doesn't matter yet since every KB doc is short enough to be
   one chunk; would matter on longer real documents.
2. **`ingest.py`'s upsert never deletes** — if a KB doc is removed or shrinks (fewer chunks than
   before), its old chunks stay orphaned in Chroma forever. Not fixed.
3. **Tool-call trigger is hardcoded** (`agent.py`'s `tool_call_node`) — decided by a Python
   `if category in {...}` check, not by the LLM dynamically via real function-calling. A more
   sophisticated agent would let the model decide whether and when to call a tool.
4. **Classifier taxonomy vs. KB category mismatch** — caught while building the eval set (3.7);
   fixed there, not in the classifier.
5. **Distance metric** — was silently defaulting to L2; fixed via `db.py` + `--reset` (3.6). The
   one item on this list that's actually resolved.
6. **Model choice** (`gpt-4o-mini`, via `AGENT_MODEL` env override) — picked for being cheap and
   current, not benchmarked against alternatives.
7. **ACR admin credentials, not managed identity** — simplest path for a demo deployment; see
   `AZURE_DEPLOYMENT.md` for the production alternative.
8. **No CI/CD** — the deploy script is run manually rather than triggered by a pipeline.

Update this list as new trade-offs get made or old ones get resolved — it should always reflect
the current, real state of the code, not a stale snapshot.
