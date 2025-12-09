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
        service_confidence_thresholds={"SOURCE_A": 1.0, "SOURCE_B": 0.3},
        service_scoring_metrics={"SOURCE_A": "confidence_score", "SOURCE_B": "cosine_similarity"},
        user_email="user@example.com",  # Optional: specify user email for tracking
        decomposition=True  # Optional: enable query decomposition for complex queries
    )

    documents = retriever.invoke("How do I reset my credentials and set up secure authentication?")
    ```

Example usage (Kubernetes cluster):
    ```python
    retriever = SnykMultiSourceRetriever(
        jwt_token="your_jwt_token",
        service_names="all",
        use_k8s_cluster=True  # app_name not required when using Kubernetes
    )

    documents = retriever.invoke("How do I reset my credentials?")
    ```
"""

from __future__ import annotations

import os
import json
import socket
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import httpx
import requests
from langchain_core.callbacks import (
    AsyncCallbackManagerForRetrieverRun,
    CallbackManagerForRetrieverRun,
)
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import field_validator

import logging

# Constants
# k8s cluster related settings
K8S_MASTER_RETRIEVER_SERVICE_NAME = "cis-master-retriever"
K8S_MASTER_RETRIEVER_NAMESPACE = "cis-master-retriever"

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
    jwt_token : str, optional
        Authentication bearer token.
        Defaults to None.

    custom_headers : dict, optional
        Pre-calculated headers to use instead of auto-generating them.
        When provided, these headers are used as-is for authentication.
        Useful for S2S authentication with pre-calculated signatures.
        Defaults to None.

    Connection parameters
    -------------------
    app_name : str, optional
        Application identifier used to build the service discovery URL. This parameter
        is **required** when ``use_k8s_cluster=False`` (default) but optional when using
        Kubernetes cluster connections. Defaults to ``None``.
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
    use_k8s_cluster : bool, optional
        Whether to use k8s cluster for internal DNS calls.
        Defaults to ``False``.
    k8s_master_retriever_service_name : str, optional
        Kubernetes service name. Used when ``use_k8s_cluster=True``.
        Defaults to ``cis-master-retriever``.
    k8s_master_retriever_namespace : str, optional
        Kubernetes namespace. Used when ``use_k8s_cluster=True``.
        Defaults to ``cis-master-retriever``.

    Retrieval parameters
    -------------------
    service_names : str | list[str]
        Either the string "all" (query every backend) or a list of
        service names (e.g., ["SOURCE_A", "SOURCE_B"]).
    service_max_documents : dict[str, int], optional
        Dictionary mapping service names to their max document limits.
    service_confidence_thresholds : dict[str, float], optional
        Dictionary mapping service names to confidence thresholds.
    service_scoring_metrics : dict[str, str], optional
        Dictionary mapping service names to scoring metric types.
        Valid values: "confidence_score" (default) or "cosine_similarity" (deterministic).
    service_filters : dict[str, dict], optional
        Dictionary mapping service names to filter objects.
    grading : bool, optional
        If set, include grading in the payload. Defaults to None (not sent).
    decomposition : bool, optional
        If set to True, enables query decomposition to break complex queries into
        subproblems and concepts. When enabled, also auto-enables grading for better
        result filtering. Defaults to None (not sent).
    user_email : str, optional
        Email address of the user making the request. Used for tracking and analytics.
        Defaults to None (not sent).

    """

    # Required parameters
    jwt_token: Optional[str] = None
    app_name: Optional[str] = None

    s2s_api_key_id: Optional[str] = None
    s2s_secret_key: Optional[str] = None
    use_s2s_auth: bool = False

    # Connection configuration
    process_type: str = "worker"
    port: int = 5000
    specific_dyno: Optional[str] = None
    timeout: int = 30
    verify_ssl: bool = True

    # Kubernetes cluster configuration
    use_k8s_cluster: bool = False
    k8s_master_retriever_service_name: str = K8S_MASTER_RETRIEVER_SERVICE_NAME
    k8s_master_retriever_namespace: str = K8S_MASTER_RETRIEVER_NAMESPACE

    # Service parameters
    service_names: Union[str, List[str]]
    service_max_documents: Optional[Dict[str, Any]] = None
    service_confidence_thresholds: Optional[Dict[str, Any]] = None
    service_scoring_metrics: Optional[Dict[str, Any]] = None
    service_filters: Optional[Dict[str, Any]] = None

    # Additional parameters
    grading: Optional[bool] = None
    decomposition: Optional[bool] = None
    user_email: Optional[str] = None

    @field_validator('service_max_documents', 'service_confidence_thresholds', 
                     'service_scoring_metrics', 'service_filters', mode='before')
    @classmethod
    def allow_none_values(cls, v):
        """Allow None values within the dictionaries."""
        if v is None:
            return v
        # If it's a dict, return as-is (None values are allowed)
        if isinstance(v, dict):
            return v
        return v

    def _get_search_url(self):
        """Build the search URL using DNS Service Discovery or Kubernetes cluster DNS."""
        if self.use_k8s_cluster:
            # Build Kubernetes cluster URL with fixed service and namespace
            dns_name = f"{self.k8s_master_retriever_service_name}.{self.k8s_master_retriever_namespace}.svc.cluster.local"
            url = f"http://{dns_name}/search"
            logger.debug("🔗 Using Kubernetes cluster URL: %s", url)

        else:
            # For non-Kubernetes connections, app_name is required
            if self.app_name is None:
                raise ValueError("app_name is required when use_k8s_cluster=False")

            # Determine DNS name based on Dyno configuration
            if self.specific_dyno:
                # Target a specific dyno if requested
                dns_name = f"{self.specific_dyno}.{self.process_type}.{self.app_name}.app.localspace"
            else:
                # Use round-robin DNS distribution across dynos
                dns_name = f"{self.process_type}.{self.app_name}.app.localspace"

            url = f"http://{dns_name}:{self.port}/search"

            try:
                # Attempt to resolve DNS to confirm connectivity
                socket.getaddrinfo(
                    dns_name, self.port, socket.AF_INET, socket.SOCK_STREAM
                )
                logger.debug("✅ DNS resolution confirmed for %s", dns_name)
            except socket.gaierror as e:  # pylint: disable=broad-except
                logger.warning(
                    "⚠️ DNS resolution check failed for %s: %s", dns_name, str(e)
                )

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
            
            # Add S2S signature if enabled
            if self.use_s2s_auth:
                parsed = urlparse(search_url)
                path = parsed.path or "/"
                body = json.dumps(payload, sort_keys=True)
                headers = self._add_s2s_signature(headers, "POST", path, body)
                
                logger.info("🚀 Sending sync S2S-authenticated search request -> %s", search_url)
                response = requests.post(
                    search_url,
                    data=body,  # Use data instead of json to preserve body for signature
                    headers=headers,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                )
            else:
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

            # Add S2S signature if enabled
            if self.use_s2s_auth:
                parsed = urlparse(search_url)
                path = parsed.path or "/"
                body = json.dumps(payload, sort_keys=True)
                headers = self._add_s2s_signature(headers, "POST", path, body)
                logger.info("🚀 (async) Sending search request with S2S auth -> %s", search_url)

                async with httpx.AsyncClient(
                    timeout=self.timeout, verify=self.verify_ssl
                ) as client:
                    response = await client.post(search_url, data=body, headers=headers)
            else:
                logger.info("🚀 (async) Sending search request with JWT auth -> %s", search_url)
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
    
        # S2S Authentication (if enabled)
        if self.use_s2s_auth and self.s2s_api_key_id and self.s2s_secret_key:
            logger.debug("🔐 Using S2S authentication")
            # We'll add S2S headers in the request methods since we need method/path/body
            headers["X-API-Key"] = self.s2s_api_key_id
            # Note: Signature, timestamp, nonce will be added in request methods
        
        # JWT Authentication (fallback or additional)
        elif self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"
            logger.debug("🔑 Using JWT token for authentication")
        else:
            logger.warning("⚠️ No authentication provided. Request may fail")
        
        return headers

    def _add_s2s_signature(
        self, headers: Dict[str, str], 
        method: str, 
        path: str, 
        body: str
    ) -> Dict[str, str]:
        """Add S2S signature headers to the request."""
        import hashlib
        import hmac
        import secrets
        import time
        
        if not (self.use_s2s_auth and self.s2s_secret_key):
            return headers
        
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        body_hash = hashlib.sha256(body.encode()).hexdigest()
        canonical = f"{method}|{path}|{timestamp}|{nonce}|{body_hash}"
        
        signature = hmac.new(
            self.s2s_secret_key.encode(),
            canonical.encode(),
            hashlib.sha256
        ).hexdigest()
        
        headers["X-Timestamp"] = timestamp
        headers["X-Nonce"] = nonce
        headers["X-Signature"] = signature
        
        return headers

    def _build_payload(self, query: str) -> Dict[str, Any]:
        """Build the JSON payload for the API request."""
        payload = {"query": query}

        # ---------------------------
        # Build services section from flattened parameters
        # ---------------------------
        services_list: List[Dict[str, Any]] = []
        names: List[str] = []

        if isinstance(self.service_names, str):
            if self.service_names.lower() == "all":
                # special keyword: query every backend, no per-service settings applied
                services_list = [{"service": "all"}]
            else:
                names = [self.service_names]
        else:
            names = self.service_names or []

        # Build detailed service objects when we have explicit service names
        for service_name in names:
            service_obj = {"service": service_name}

            # Add max_documents if available for this service (None values allowed)
            if (
                self.service_max_documents is not None
                and service_name in self.service_max_documents
            ):
                service_obj["max_documents"] = self.service_max_documents[service_name]

            # Add confidence_threshold if available for this service (None values allowed)
            if (
                self.service_confidence_thresholds is not None
                and service_name in self.service_confidence_thresholds
            ):
                service_obj["confidence_threshold"] = (
                    self.service_confidence_thresholds[service_name]
                )

            # Add scoring_metric if available for this service (None values allowed)
            if (
                self.service_scoring_metrics is not None
                and service_name in self.service_scoring_metrics
            ):
                service_obj["scoring_metric"] = (
                    self.service_scoring_metrics[service_name]
                )

            # Add filter if available for this service (None values allowed)
            if self.service_filters is not None and service_name in self.service_filters:
                service_obj["filter"] = self.service_filters[service_name]

            services_list.append(service_obj)

        # Only add services to payload if we have any
        if services_list:
            payload["services"] = services_list

        # Add grading if specified
        if self.grading is not None:
            payload["grading"] = self.grading

        # Add decomposition if specified
        if self.decomposition is not None:
            payload["decomposition"] = self.decomposition

        # Add user_email if specified
        if self.user_email is not None:
            payload["user_email"] = self.user_email

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
