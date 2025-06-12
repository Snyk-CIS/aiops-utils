"""Test script for SnykMultiSourceRetriever.

Runs several scenarios against the retriever and prints a short summary of the
number of documents returned for each case. Requires the following environment
variables to be set:

* ``JWT_TOKEN`` – bearer token used by the retriever
* ``APP_NAME``  – application name used for service-discovery DNS
* ``SERVICE_NAMES`` – comma-separated list or JSON list of service names

This script is intended to be executed inside CI (see ``.github/workflows``) or
locally for quick validation.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Dict, List

from aiops_utils.retrievers import SnykMultiSourceRetriever
import logging

logger = logging.getLogger("aiops-utils")
# ---------------------------------------------------------------------------#
# Environment & sanity checks
# ---------------------------------------------------------------------------#
jwt_token: str | None = os.getenv("JWT_TOKEN")
app_name: str | None = os.getenv("APP_NAME")

if not jwt_token or not app_name:
    logger.error(
        "❌ Environment variables JWT_TOKEN, APP_NAME and SERVICE_NAMES are required. Received JWT_TOKEN=%s, APP_NAME=%s",
        bool(jwt_token),
        bool(app_name),
    )
    sys.exit(1)

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
        "description": "Baseline – secret service names",
        "service_names": "all",
    },
    # 2) Single source with grading disabled
    {
        "description": "Single data source (max 30 docs) - no grading",
        "service_names": [source_a],
        "service_max_documents": {source_a: 30},
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
        "service_filters": {source_a: {"SOURCE": source_a_filter}},
    },
    # 5) Multi-source with max documents
    {
        "description": "Multi-source with max documents",
        "service_names": [source_a, source_b],
        "service_max_documents": {source_a: 4, source_b: 2},
    },
    # 6) Multi-source with confidence thresholds
    {
        "description": "Multi-source with confidence thresholds",
        "service_names": [source_a, source_b],
        "service_confidence_thresholds": {source_a: 0.8, source_b: 0.9},
    },
    # 7) Rerank configuration test
    {
        "description": "Rerank parameters test",
        "service_names": "all",
        "rerank_confidence_threshold": 0.9,
    },
]

QUERY = "What is Snyk Code?"  # simple query for smoke-test

# ---------------------------------------------------------------------------#
# Execution helpers
# ---------------------------------------------------------------------------#


def run_test_case(case: Dict[str, Any]) -> None:
    """Execute a single test case (sync or async) and log the results."""
    async_flag = case.pop("async_call", False)
    description = case.pop("description")  # do not pass downstream to retriever

    logger.info("\n🧪 Running test case ⇒ %s", description)

    try:
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

        logger.info("✅ %s — received %d documents", description, len(documents))

        if documents:
            logger.info("📄 First doc snippet: %.120s…", documents[0].page_content)
    # pylint: disable=broad-except
    except Exception as exc:
        logger.error("💥 %s — failed with error: %s", description, exc)


if __name__ == "__main__":
    for test_case in TEST_CASES:
        # Each test runs independently so failures don't abort subsequent cases
        run_test_case(test_case.copy())
