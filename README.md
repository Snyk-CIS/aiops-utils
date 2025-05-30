# AI Operations Utilities
A collection of lightweight, reusable Python helpers built and maintained by the **Snyk AI Operations Team**.

---

## ✨ Features

| Area | Module | What it does |
| --- | --- | --- |
| Retrieval | `aiops_utils.retrievers.SnykMultiSourceRetriever` | LangChain-compatible retriever that queries a remote multi-source search service, merges the results, then returns them as `langchain_core.Document` objects. |

---

## 📦 Installation

```bash
pip install git+https://github.com/Snyk-CIS/aiops-utils.git
```

Python ≥ 3.10 is required.

---

## 🚀 Quick-start

### 1. Retrieve Documents with LangChain

```python
from aiops_utils.retrievers import SnykMultiSourceRetriever

retriever = SnykMultiSourceRetriever(
    jwt_token="<YOUR_JWT_TOKEN>",     # Bearer token for authentication
    app_name="my-search-service",     # DNS label of the backend application
    service_names="all",              # or a list like ["SOURCE_A", "SOURCE_B"]
)

results = retriever.invoke("How do I reset my credentials?")
for doc in results:
    print(doc.page_content)
```

Key constructor flags:

| Parameter | Purpose |
|-----------|---------|
| `jwt_token` | Auth bearer token passed in the `Authorization` header. |
| `app_name` | Name of the search service (used for DNS discovery). |
| `service_names` | Either `'all'` or a list of specific back-end sources. |
| `service_max_documents` / `service_confidence_thresholds` | Per-source overrides. |
| `rerank_max_documents` / `rerank_confidence_threshold` | Control the re-ranking stage. |
