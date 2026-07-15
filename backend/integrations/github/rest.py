"""Authenticated JSON client for the GitHub REST API.

Shares the connector-neutral `Transport` (so the rate governor wraps it) and raises the
vendor-free `CapabilityError` on >=400, exactly like the Atlassian client.
"""
from __future__ import annotations

import urllib.parse

from integrations.transport import Transport, default_transport
from integrations.types import CapabilityError

from .config import GithubConfig

_API_VERSION = "2022-11-28"


class GithubRest:
    """`path` is relative to the API root (e.g. `/repos/{owner}/{repo}/pulls`)."""

    def __init__(self, config: GithubConfig, transport: Transport | None = None):
        self._cfg = config
        self._transport = transport or default_transport

    def request(self, method: str, path: str, *, body: object | None = None,
                query: dict | None = None) -> object:
        url = self._cfg.api_url + path
        if query:
            clean = {k: v for k, v in query.items() if v is not None}
            url += "?" + urllib.parse.urlencode(clean)
        headers = {
            "Authorization": self._cfg.auth_header(),
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _API_VERSION,
            "User-Agent": "sdlc-platform",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        status, data = self._transport(method, url, headers, body)
        if status >= 400:
            raise CapabilityError(
                f"GitHub {method} {path} -> {status}", status=status, detail=data
            )
        return data

    def graphql(self, query: str, variables: dict | None = None) -> object:
        """POST a GraphQL query/mutation to the v4 endpoint through the same shared Transport
        (so the rate governor still wraps it). GraphQL returns HTTP 200 even for logical errors,
        so a non-empty `errors` array is raised as CapabilityError too — not silently ignored."""
        headers = {
            "Authorization": self._cfg.auth_header(),
            "Content-Type": "application/json",
            "User-Agent": "sdlc-platform",
        }
        status, data = self._transport(
            "POST", self._cfg.graphql_url, headers,
            {"query": query, "variables": variables or {}},
        )
        if status >= 400:
            raise CapabilityError(
                f"GitHub GraphQL -> {status}", status=status, detail=data
            )
        errors = (data or {}).get("errors") if isinstance(data, dict) else None
        if errors:
            raise CapabilityError(f"GitHub GraphQL error: {errors}", detail=data)
        return data
