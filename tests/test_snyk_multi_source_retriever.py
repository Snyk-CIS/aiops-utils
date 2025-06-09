import os
from aiops_utils.retrievers.snyk_multi_source_retriever import SnykMultiSourceRetriever
import logging

logger = logging.getLogger(__name__)

REQUIRED_VARS = ["JWT_TOKEN", "APP_NAME", "SERVICE_NAMES"]


def _missing_env():
    return [v for v in REQUIRED_VARS if not os.getenv(v)]


missing = _missing_env()
if missing:
    logger.error("❌ Missing required environment variables: %s", ", ".join(missing))
    raise SystemExit(1)

# Test simple retrieval and all data sources - Check all services were run
logger.info(
    "🧪 Running all-services retrieval with service_names='All'",
)
retriever = SnykMultiSourceRetriever(
    jwt_token=os.getenv("JWT_TOKEN"),
    app_name=os.getenv("APP_NAME"),
    service_names="All",
)
documents = retriever.invoke("What does Snyk Open Source and Snyk Code do?")
logger.info("✅ Retrieved %d documents with all services", len(documents))

DOCS_SERVICE = os.getenv("SERVICE_NAMES")

# Test retrieval with service filters and specific data source - Check the confidence threshold
logger.info(
    "🧪 Running retrieval with service_names=['%s'] and confidence threshold 1.0",
    DOCS_SERVICE,
)
retriever = SnykMultiSourceRetriever(
    jwt_token=os.getenv("JWT_TOKEN"),
    app_name=os.getenv("APP_NAME"),
    service_names=[DOCS_SERVICE],
    service_confidence_thresholds={DOCS_SERVICE: 1.0},
)
documents = retriever.invoke("What does Snyk Open Source and Snyk Code do?")
logger.info("✅ Retrieved %d documents with confidence threshold", len(documents))

# Test retrieval with service filters and specific data source - Check the max documents
logger.info(
    "🧪 Running retrieval with service_names=['%s'] and max_documents=5", DOCS_SERVICE
)
retriever = SnykMultiSourceRetriever(
    jwt_token=os.getenv("JWT_TOKEN"),
    app_name=os.getenv("APP_NAME"),
    service_names=[DOCS_SERVICE],
    service_max_documents={DOCS_SERVICE: 5},
)
documents = retriever.invoke("What does Snyk Open Source and Snyk Code do?")
logger.info("✅ Retrieved %d documents with max_documents", len(documents))

# Test retrieval with reranking and specific data source - Check the rerank
logger.info(
    "🧪 Running retrieval with rerank_max_documents=5 and rerank_confidence_threshold=0.8 and service_names=['%s']",
    DOCS_SERVICE,
)
retriever = SnykMultiSourceRetriever(
    jwt_token=os.getenv("JWT_TOKEN"),
    app_name=os.getenv("APP_NAME"),
    service_names=[DOCS_SERVICE],
    rerank_max_documents=5,
    rerank_confidence_threshold=0.8,
)
documents = retriever.invoke("What does Snyk Open Source and Snyk Code do?")
logger.info("✅ Retrieved %d documents with reranking", len(documents))
