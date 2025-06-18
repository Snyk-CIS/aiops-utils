"""Test script for SnykMultiSourceRetriever.

Runs several scenarios against the retriever and prints a short summary of the
number of documents returned for each case. Requires the following environment
variables to be set:

* ``JWT_TOKEN`` – bearer token used by the retriever
* ``APP_NAME``  – application name used for service-discovery DNS

This script is intended to be executed inside CI (see ``.github/workflows``) or
locally for quick validation.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Dict, List

from aiops_utils.retrievers import SnykMultiSourceRetriever
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

logger = logging.getLogger("aiops-utils")
# ---------------------------------------------------------------------------#
# Environment & sanity checks
# ---------------------------------------------------------------------------#
jwt_token: str | None = os.getenv("JWT_TOKEN")
app_name: str | None = os.getenv("APP_NAME")

if not jwt_token or not app_name:
    logger.error(
        "❌ Environment variables JWT_TOKEN, APP_NAME are required. Received JWT_TOKEN=%s, APP_NAME=%s",
        bool(jwt_token),
        bool(app_name),
    )
    sys.exit(1)

# Get Heroku direct URL if available (preferred for GitHub Actions and local testing)
use_direct_url = os.getenv("USE_DIRECT_URL", "true").lower() in ("true", "1", "yes")
direct_url = os.getenv("DIRECT_URL")

if use_direct_url and not direct_url:
    logger.warning("⚠️ USE_DIRECT_URL is enabled but no DIRECT_URL is provided")

# Patch the _get_search_url method before any retrievers are created
if use_direct_url and direct_url:
    # Store original method for restoration at the end
    original_get_search_url = SnykMultiSourceRetriever._get_search_url

    # Define replacement method that returns the direct Heroku URL
    def direct_url_method(self):
        logger.info("🔗 Using direct Heroku URL: %s", direct_url)
        return direct_url

    # Apply the patch globally
    SnykMultiSourceRetriever._get_search_url = direct_url_method
    logger.info("👉 Patched retriever to use direct URL mode")

# Get source names from environment if available
source_a = os.getenv("TEST_SOURCE_A")
source_b = os.getenv("TEST_SOURCE_B")
source_a_filter = os.getenv("TEST_FILTER_A")

# ---------------------------------------------------------------------------#
# Test cases definition
# ---------------------------------------------------------------------------#
TEST_CASES: List[Dict[str, Any]] = [
    # 1) Baseline using SERVICE_NAMES provided via secret
    {
        "description": "Baseline – all sources",
        "service_names": "all",
        "grading": False,
    },
    # 2) Single source with grading disabled
    {
        "description": "Single data source (max 5 docs) - no grading",
        "service_names": [source_a],
        "service_max_documents": {source_a: 5},
        "grading": False,
    },
    # 3) Single source with grading enabled
    {
        "description": "Single data source (max 30 docs) - with grading",
        "service_names": [source_a],
        "service_max_documents": {source_a: 30},
        "grading": True,
    },
    # 4) Source with filter applied
    {
        "description": "Single source with filter",
        "service_names": [source_a],
        "service_filters": {source_a: {"@eq": {"source": source_a_filter}}},
        "grading": False,
    },
    # 5) Multi-source with max documents
    {
        "description": "Multi-source with max documents",
        "service_names": [source_a, source_b],
        "service_max_documents": {source_a: 4, source_b: 2},
        "grading": False,
    },
    # 6) Multi-source with confidence thresholds
    {
        "description": "Multi-source with confidence thresholds",
        "service_names": [source_a, source_b],
        "service_confidence_thresholds": {source_a: 3.0, source_b: 2.0},
        "grading": False,
    },
    # 7) Rerank configuration test
    {
        "description": "Rerank parameters test",
        "service_names": "all",
        "rerank_confidence_threshold": 0.95,
        "grading": True,
    },
]

QUERY = "What is Snyk Code?"  # simple query for smoke-test

# ---------------------------------------------------------------------------#
# Execution helpers
# ---------------------------------------------------------------------------#

# Store per-test run statistics so we can print a summary at the end
RESULTS: List[Dict[str, Any]] = []


def run_test_case(case: Dict[str, Any]) -> None:
    """Execute a single test case (sync or async) and log the results."""
    async_flag = case.pop("async_call", False)
    description = case.pop("description")  # do not pass downstream to retriever

    logger.info("\n🧪 Running test case ⇒ %s", description)

    try:
        # Create retriever with all parameters (direct URL already patched if enabled)
        retriever = SnykMultiSourceRetriever(
            jwt_token=jwt_token,
            app_name=app_name,
            **case,  # remaining keys map to retriever kwargs
        )

        # Choose sync or async execution path
        if async_flag:
            documents = asyncio.run(retriever.ainvoke(QUERY))
        else:
            documents = retriever.invoke(QUERY)

        # Determine whether the document count is sensible (>0)
        if len(documents) == 0:
            verdict_emoji = "🔴"  # automatic fail
        elif len(documents) == 1:
            verdict_emoji = "🟠"  # suspicious, needs review
        else:
            verdict_emoji = "✅"
        logger.info(
            "%s %s — received %d documents", verdict_emoji, description, len(documents)
        )

        # Persist results so we can output a summary after all tests have run
        RESULTS.append(
            {
                "description": description,
                "count": len(documents),
                "verdict": verdict_emoji,
            }
        )

    # pylint: disable=broad-except
    except Exception as exc:
        logger.error("💥 %s — failed with error: %s", description, exc)
        RESULTS.append(
            {
                "description": description,
                "count": 0,
                "verdict": "🔴",
            }
        )


if __name__ == "__main__":
    try:
        for test_case in TEST_CASES:
            # Each test runs independently so failures don't abort subsequent cases
            run_test_case(test_case.copy())
    finally:
        # Print high-level summary for quick human review
        logger.info("\n📊 Test run summary")
        for result in RESULTS:
            logger.info(
                "%s %s ⇒ %d documents",
                result["verdict"],
                result["description"],
                result["count"],
            )

        # Restore original method if we patched it
        if use_direct_url and direct_url and "original_get_search_url" in globals():
            SnykMultiSourceRetriever._get_search_url = original_get_search_url
