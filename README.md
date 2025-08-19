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
    jwt_token="your_jwt_token",
    app_name="your_app_name",
    service_names=["SOURCE_A", "SOURCE_B"],
    service_max_documents={"SOURCE_A": 5, "SOURCE_B": 3},
    service_confidence_thresholds={"SOURCE_A": 0.9, "SOURCE_B": 1.0},
    service_filters={"SOURCE_B": {"@eq": {"author": "example_user"}}},
    user_email="user@example.com",
    grading=True
)

results = retriever.invoke("How do I rotate my credentials?")
for doc in results:
    print(doc.page_content)
```

Key constructor flags:

| Parameter | Required | Purpose |
|-----------|----------|---------|
| `jwt_token` | ✅ | Auth bearer token passed in the `Authorization` header. |
| `app_name` | ✅ | Name of the search service (used for DNS discovery). |
| `service_names` | ✅ | Either `'all'` or a list of specific back-end sources. |
| `service_max_documents` | ❌ | Per-source override for maximum number of documents to return. |
| `service_confidence_thresholds` | ❌ | Per-source override for minimum confidence scores. |
| `service_filters` | ❌ | Dictionary mapping service names to filter objects. |
| `grading` | ❌ | When `True`, the backend returns per-token confidence scores. Defaults to `None`. |
| `user_email` | ❌ | Email address of the user making the request. Used for tracking. Defaults to `None`. |
