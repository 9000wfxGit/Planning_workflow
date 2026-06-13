"""Read-only web search providers for the questioning agent."""

from __future__ import annotations

from typing import Protocol

import httpx

from planning_workflow.domain.errors import ConfigurationError
from planning_workflow.domain.models import SearchResult

from .config import Settings


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        ...


class SearXNGSearchProvider:
    name = "searxng"

    def __init__(self, base_url: str, http_client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._http_client = http_client

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        params = {"q": query, "format": "json"}
        client = self._http_client
        if client is not None:
            response = client.get(f"{self.base_url}/search", params=params)
        else:
            with httpx.Client(timeout=10.0) as owned_client:
                response = owned_client.get(f"{self.base_url}/search", params=params)
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])
        output: list[SearchResult] = []
        for item in results[:max_results]:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            output.append(
                SearchResult(
                    title=str(item.get("title", "")),
                    url=str(item["url"]),
                    snippet=str(item.get("content", "")),
                    source=self.name,
                )
            )
        return output


class BraveSearchProvider:
    name = "brave"

    def __init__(self, api_key: str, http_client: httpx.Client | None = None) -> None:
        self.api_key = api_key.strip()
        self._http_client = http_client

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not self.api_key or self.api_key == "put_api_key_here":
            raise ConfigurationError("BRAVE_SEARCH_API_KEY is not configured.")
        headers = {"X-Subscription-Token": self.api_key, "Accept": "application/json"}
        params = {"q": query, "count": max_results}
        url = "https://api.search.brave.com/res/v1/web/search"
        client = self._http_client
        if client is not None:
            response = client.get(url, headers=headers, params=params)
        else:
            with httpx.Client(timeout=10.0) as owned_client:
                response = owned_client.get(url, headers=headers, params=params)
        response.raise_for_status()
        payload = response.json()
        results = payload.get("web", {}).get("results", [])
        output: list[SearchResult] = []
        for item in results[:max_results]:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            output.append(
                SearchResult(
                    title=str(item.get("title", "")),
                    url=str(item["url"]),
                    snippet=str(item.get("description", "")),
                    source=self.name,
                )
            )
        return output


class SearchProviderChain:
    name = "chain"

    def __init__(self, providers: list[SearchProvider]) -> None:
        self.providers = providers

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        for provider in self.providers:
            try:
                results = provider.search(query, max_results=max_results)
            except Exception:
                continue
            if results:
                return results
        return []


def build_search_provider(settings: Settings) -> SearchProviderChain:
    providers: list[SearchProvider] = []
    for name in settings.search_providers:
        if name == "searxng":
            providers.append(SearXNGSearchProvider(settings.searxng_base_url))
        elif name == "brave":
            providers.append(BraveSearchProvider(settings.brave_search_api_key))
    return SearchProviderChain(providers)
