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
    grading=True,
    decomposition=True
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
| `decomposition` | ❌ | When `True`, enables query decomposition to break complex queries into subproblems. Auto-enables grading. Defaults to `None`. |
| `user_email` | ❌ | Email address of the user making the request. Used for tracking. Defaults to `None`. |

---

## 🛠️ Development

For maintainers and contributors working on the `aiops-utils` package.

### Building the Package

Use the provided script to rebuild the package:

```bash
./scripts/rebuild_package.sh
```

This script will:
- ✅ Check your environment
- 🔢 Optionally increment the version
- 🧹 Clean old build artifacts
- 🔨 Build wheel and source distributions
- 📋 Show next steps for deployment

### Manual Build Steps

If you prefer manual control:

```bash
# 1. Update version in pyproject.toml (if needed)
# 2. Clean and build
rm -rf dist/ build/ src/aiops_utils.egg-info/
pip install --upgrade build wheel setuptools
python -m build

# 3. Commit and push
git add . && git commit -m "Release version X.X.X" && git push
```

### Deployment to Production

1. **Push to Git** (apps install from Git, not PyPI):
   ```bash
   git push origin main
   ```

2. **Production apps will automatically get the latest version** on their next deployment

3. **Force update existing deployments** (if needed):
   ```bash
   pip install --upgrade --force-reinstall git+https://github.com/Snyk-CIS/aiops-utils.git
   ```
