"""Custom LangChain retriever for querying a remote multi-source retrieval API.

This class is a drop-in `BaseRetriever` that builds the JSON payload from a set of
optional constructor parameters and a runtime query string. It supports querying
multiple information sources with configurable parameters.

Example usage (simple):
    ```python
    from snyk_multi_source_retriever import SnykMultiSourceRetriever

    retriever = SnykMultiSourceRetriever(jwt_token="your_jwt_token", service_names="all")
    documents = retriever.invoke("How do I reset my credentials?")
    ```

Example usage (advanced):
    ```python
    retriever = SnykMultiSourceRetriever(
        jwt_token="your_jwt_token",
        app_name="your_app_name",
        service_names=["SOURCE_A", "SOURCE_B"],
        service_max_documents={"SOURCE_A": 5, "SOURCE_B": 3},
        service_confidence_thresholds={"SOURCE_A": 1.0, "SOURCE_B": 1.0},
        rerank_max_documents=5,
        rerank_confidence_threshold=0.8
    )

    documents = retriever.invoke("How do I reset my credentials?")
    ```
"""

from __future__ import annotations

import os
import socket
from typing import Any, Dict, List, Optional, Union

import httpx
import requests
from langchain_core.callbacks import (
    AsyncCallbackManagerForRetrieverRun,
    CallbackManagerForRetrieverRun,
)
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

import logging

logger = logging.getLogger(__name__)

# Check environment variable and set debug logging if needed
environment = os.environ.get("environment")
if environment in ["DEV"]:
    logger.setLevel(logging.DEBUG)
    logger.debug("🔧 Setting logger to DEBUG level in %s environment", environment)

# --------------------------------------------------------------------------------------
# Retriever implementation
# --------------------------------------------------------------------------------------


class SnykMultiSourceRetriever(BaseRetriever):
    """LangChain retriever for a remote multi-source retrieval API.

    Parameters
    ----------
    jwt_token : str
        Authentication bearer token.

    Connection parameters
    -------------------
    app_name : str
        Application identifier used to build the service discovery URL. This parameter
        is **required** and must be provided when creating the retriever instance.
    process_type : str, optional
        Type of process to connect to. Used to build the DNS service discovery URL.
        Defaults to ``worker``.
    port : int, optional
        Port number to connect to. Defaults to ``5000``.
    specific_dyno : str, optional
        Specific dyno to query. If provided, targets that specific dyno instead of
        using round-robin DNS. Defaults to ``None``.
    timeout : int, optional
        Timeout (seconds) for HTTP requests. Defaults to ``30``.
    verify_ssl : bool, optional
        Whether to verify SSL/TLS certificates. Defaults to ``True``.

    Retrieval parameters
    -------------------
    service_names : str | list[str]
        Either the string "all" (query every backend) or a list of
        service names (e.g., ["SOURCE_A", "SOURCE_B"]).
    service_max_documents : dict[str, int], optional
        Dictionary mapping service names to their max document limits.
    service_confidence_thresholds : dict[str, float], optional
        Dictionary mapping service names to confidence thresholds.
    service_filters : dict[str, dict], optional
        Dictionary mapping service names to filter objects.
    rerank_max_documents : int, optional
        Maximum number of documents after reranking.
    rerank_confidence_threshold : float, optional
        Confidence threshold for reranking.

    """

    # Required parameters
    jwt_token: str
    app_name: str

    # Connection configuration
    process_type: str = "worker"
    port: int = 5000
    specific_dyno: Optional[str] = None
    timeout: int = 30
    verify_ssl: bool = True

    # Service parameters
    service_names: Union[str, List[str]]
    service_max_documents: Optional[Dict[str, int]] = None
    service_confidence_thresholds: Optional[Dict[str, float]] = None
    service_filters: Optional[Dict[str, Dict]] = None

    # Rerank parameters
    rerank_max_documents: Optional[int] = None
    rerank_confidence_threshold: Optional[float] = None

    def _get_search_url(self):
        """Build the search URL using DNS Service Discovery."""
        # Determine DNS name based on configuration
        if self.specific_dyno:
            # Target a specific dyno if requested
            dns_name = f"{self.specific_dyno}.{self.process_type}.{self.app_name}.app.localspace"
        else:
            # Use round-robin DNS distribution across dynos
            dns_name = f"{self.process_type}.{self.app_name}.app.localspace"

        url = f"http://{dns_name}:{self.port}/search"

        try:
            # Attempt to resolve DNS to confirm connectivity
            socket.getaddrinfo(dns_name, self.port, socket.AF_INET, socket.SOCK_STREAM)
            logger.debug("✅ DNS resolution confirmed for %s", dns_name)
        except socket.gaierror as e:  # pylint: disable=broad-except
            logger.warning("⚠️ DNS resolution check failed for %s: %s", dns_name, str(e))

        return url

    # ------------------------------------------------------------------
    # BaseRetriever overrides (sync & async)
    # ------------------------------------------------------------------

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Optional[CallbackManagerForRetrieverRun] = None,
    ) -> List[Document]:
        """Synchronous retrieval implementation."""
        payload = self._build_payload(query)
        headers = self._headers()

        try:
            search_url = self._get_search_url()
            logger.info("🚀 Sending sync search request -> %s", search_url)
            response = requests.post(
                search_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            json_docs: List[Dict[str, Any]] = response.json()
            logger.debug("🔍 Retrieved %d docs", len(json_docs))
            return self._json_to_documents(json_docs)
        # pylint: disable=broad-except
        except Exception as exc:
            logger.error("💥 Sync retrieval failed: %s", exc)
            return []

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Optional[AsyncCallbackManagerForRetrieverRun] = None,
    ) -> List[Document]:
        """Native async retrieval implementation."""
        payload = self._build_payload(query)
        headers = self._headers()

        try:
            search_url = self._get_search_url()
            logger.info("🚀 (async) Sending search request -> %s", search_url)
            async with httpx.AsyncClient(
                timeout=self.timeout, verify=self.verify_ssl
            ) as client:
                response = await client.post(search_url, json=payload, headers=headers)
                response.raise_for_status()
                json_docs: List[Dict[str, Any]] = response.json()
            logger.debug("🔍 (async) Retrieved %d docs", len(json_docs))
            return self._json_to_documents(json_docs)
        # pylint: disable=broad-except
        except Exception as exc:
            logger.error("💥 Async retrieval failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        """Build request headers with authentication."""
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"
            logger.debug("🔑 Using JWT token for authentication")
        else:
            logger.warning("⚠️ No JWT token provided. Request may fail")
        return headers

    def _build_payload(self, query: str) -> Dict[str, Any]:
        """Compose the POST body based on provided optional parameters."""
        payload: Dict[str, Any] = {"query": query}

        # ---------------------------
        # Build services section from service_names parameter
        # ---------------------------
        services_list = []

        # Process service_names parameter if provided
        if isinstance(self.service_names, str):
            # "all" or single service name
            if self.service_names.lower() == "all":
                services_list = [{"service": "all"}]
            else:
                services_list = [{"service": self.service_names}]
        elif isinstance(self.service_names, list):
            # list of service names
            for service_name in self.service_names:
                service_obj = {"service": service_name}

                # Add max_documents if available for this service
                if (
                    self.service_max_documents
                    and service_name in self.service_max_documents
                ):
                    service_obj["max_documents"] = self.service_max_documents[
                        service_name
                    ]

                # Add confidence_threshold if available for this service
                if (
                    self.service_confidence_thresholds
                    and service_name in self.service_confidence_thresholds
                ):
                    service_obj["confidence_threshold"] = (
                        self.service_confidence_thresholds[service_name]
                    )

                # Add filter if available for this service
                if self.service_filters and service_name in self.service_filters:
                    service_obj["filter"] = self.service_filters[service_name]

                services_list.append(service_obj)

        # Only add services to payload if we have any
        if services_list:
            payload["services"] = services_list

        # ---------------------------
        # Build rerank section from flattened parameters
        # ---------------------------
        if (
            self.rerank_max_documents is not None
            or self.rerank_confidence_threshold is not None
        ):
            rerank_obj = {}
            if self.rerank_max_documents is not None:
                rerank_obj["max_documents"] = self.rerank_max_documents
            if self.rerank_confidence_threshold is not None:
                rerank_obj["confidence_threshold"] = self.rerank_confidence_threshold
            if rerank_obj:  # Only add if we have any parameters
                payload["rerank"] = rerank_obj

        logger.debug("📝 Built payload: %s", payload)
        return payload

    @staticmethod
    def _json_to_documents(raw: List[Dict[str, Any]]) -> List[Document]:
        """Convert raw JSON list from API into LangChain `Document`s."""
        return [
            Document(
                page_content=item.get("page_content"),
                metadata=item.get("metadata"),
            )
            for item in raw
        ]
