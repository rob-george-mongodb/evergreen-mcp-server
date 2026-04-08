"""Authentication bootstrap for standalone Evergreen GraphQL access."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Mapping

from . import DEFAULT_API_KEY_GRAPHQL_URL, DEFAULT_OIDC_GRAPHQL_URL, USER_AGENT

if TYPE_CHECKING:
    from gql import Client
    from gql.client import AsyncClientSession
    from gql.transport.exceptions import TransportError
    from graphql import DocumentNode

    from evergreen_mcp.oidc_auth import OIDCAuthManager

ResolvedAuthMethod = Literal["api_key", "oidc"]
GraphQLAuthMode = Literal["auto", "api_key", "oidc"]

logger = logging.getLogger(__name__)


class AuthBootstrapError(RuntimeError):
    """Raised when standalone GraphQL authentication bootstrap fails."""


def resolve_graphql_endpoint(
    auth_method: ResolvedAuthMethod, *, endpoint: str | None = None
) -> str:
    """Resolve the GraphQL endpoint for the selected auth method."""

    if endpoint:
        return endpoint.rstrip("/")

    if auth_method == "oidc":
        return os.getenv(
            "EVERGREEN_OIDC_GRAPHQL_URL", DEFAULT_OIDC_GRAPHQL_URL
        ).rstrip("/")

    return os.getenv(
        "EVERGREEN_API_KEY_GRAPHQL_URL", DEFAULT_API_KEY_GRAPHQL_URL
    ).rstrip("/")


@dataclass(frozen=True)
class GraphQLAuthMetadata:
    """Resolved authentication details for a connected GraphQL client."""

    auth_method: ResolvedAuthMethod
    endpoint: str
    user: str | None
    token_refresh_enabled: bool


class ConnectedEvergreenGraphQLClient:
    """Small async GraphQL client wrapper for Evergreen endpoints."""

    def __init__(
        self,
        *,
        endpoint: str,
        auth_method: ResolvedAuthMethod,
        user: str | None = None,
        api_key: str | None = None,
        bearer_token: str | None = None,
        auth_manager: OIDCAuthManager | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.auth_method = auth_method
        self.user = user
        self.api_key = api_key
        self.bearer_token = bearer_token
        self.auth_manager = auth_manager
        self._client: Client | None = None
        self._session: AsyncClientSession | None = None

        if self.auth_method == "api_key" and not (self.user and self.api_key):
            raise ValueError("API key auth requires both user and api_key")

        if self.auth_method == "oidc" and not self.bearer_token:
            raise ValueError("OIDC auth requires a bearer token")

    async def connect(self) -> ConnectedEvergreenGraphQLClient:
        """Open the underlying async GraphQL session."""

        if self._session is not None:
            return self

        from gql import Client
        from gql.transport.aiohttp import AIOHTTPTransport

        transport = AIOHTTPTransport(url=self.endpoint, headers=self._build_headers())
        self._client = Client(transport=transport)
        self._session = await self._client.connect_async(reconnecting=True)
        return self

    async def close(self) -> None:
        """Close the underlying async GraphQL session."""

        if self._session is None:
            return

        try:
            await self._session.close()
        except Exception:
            logger.warning("Error closing GraphQL session", exc_info=True)
        finally:
            self._session = None
            self._client = None

    async def execute(
        self,
        query: str | DocumentNode,
        variables: Mapping[str, Any] | None = None,
    ) -> Any:
        """Execute a GraphQL query, refreshing OIDC credentials if needed."""

        if self._session is None:
            raise RuntimeError("Client not connected. Call connect() first.")

        from gql import gql
        from gql.transport.exceptions import TransportError

        document = gql(query) if isinstance(query, str) else query
        variable_values = dict(variables) if variables is not None else None

        try:
            return await self._session.execute(
                document,
                variable_values=variable_values,
            )
        except TransportError as exc:
            if not await self._try_refresh_after_auth_error(exc):
                raise

        if self._session is None:
            raise RuntimeError("Client not connected after credential refresh.")

        return await self._session.execute(
            document,
            variable_values=variable_values,
        )

    @property
    def session(self) -> AsyncClientSession:
        """Return the connected gql session."""

        if self._session is None:
            raise RuntimeError("Client not connected. Call connect() first.")
        return self._session

    def _build_headers(self) -> dict[str, str]:
        common_headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }

        if self.auth_method == "oidc":
            return {
                **common_headers,
                "Authorization": f"Bearer {self.bearer_token}",
                "x-kanopy-internal-authorization": f"Bearer {self.bearer_token}",
            }

        return {
            **common_headers,
            "Api-User": self.user or "",
            "Api-Key": self.api_key or "",
        }

    async def _try_refresh_after_auth_error(self, error: Exception) -> bool:
        if self.auth_method != "oidc" or self.auth_manager is None:
            return False

        error_text = str(error).lower()
        if "401" not in error_text and "unauthorized" not in error_text:
            return False

        token_data = await self.auth_manager.refresh_token()
        access_token = (token_data or {}).get("access_token")
        if not access_token:
            return False

        self.bearer_token = access_token
        await self.close()
        await self.connect()
        return True


@dataclass
class AuthenticatedGraphQLContext:
    """Connected GraphQL client plus resolved auth metadata."""

    client: ConnectedEvergreenGraphQLClient
    metadata: GraphQLAuthMetadata
    auth_manager: OIDCAuthManager | None = None


class EvergreenGraphQLBootstrap:
    """Async context manager that bootstraps authenticated GraphQL access."""

    def __init__(
        self,
        *,
        auth_mode: GraphQLAuthMode = "auto",
        user: str | None = None,
        api_key: str | None = None,
        endpoint: str | None = None,
        auth_manager: OIDCAuthManager | None = None,
    ) -> None:
        self.auth_mode = auth_mode
        self.user = user
        self.api_key = api_key
        self.endpoint = endpoint
        self.auth_manager = auth_manager
        self._context: AuthenticatedGraphQLContext | None = None

    async def __aenter__(self) -> AuthenticatedGraphQLContext:
        return await self.connect()

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        _ = exc_type, exc_value, traceback
        await self.close()

    async def connect(self) -> AuthenticatedGraphQLContext:
        """Resolve authentication, connect a client, and return context."""

        if self._context is not None:
            return self._context

        auth_method = self._resolve_auth_method()
        endpoint = resolve_graphql_endpoint(auth_method, endpoint=self.endpoint)

        if auth_method == "api_key":
            user, api_key = self._resolve_api_key_credentials()
            client = ConnectedEvergreenGraphQLClient(
                endpoint=endpoint,
                auth_method=auth_method,
                user=user,
                api_key=api_key,
            )
            metadata = GraphQLAuthMetadata(
                auth_method=auth_method,
                endpoint=endpoint,
                user=user,
                token_refresh_enabled=False,
            )
            auth_manager = None
        else:
            auth_manager = self.auth_manager or self._create_oidc_auth_manager()
            if not await auth_manager.ensure_authenticated():
                raise AuthBootstrapError("OIDC authentication failed")

            if not auth_manager.access_token:
                raise AuthBootstrapError("OIDC authentication did not yield a token")

            client = ConnectedEvergreenGraphQLClient(
                endpoint=endpoint,
                auth_method=auth_method,
                user=auth_manager.user_id,
                bearer_token=auth_manager.access_token,
                auth_manager=auth_manager,
            )
            metadata = GraphQLAuthMetadata(
                auth_method=auth_method,
                endpoint=endpoint,
                user=auth_manager.user_id,
                token_refresh_enabled=True,
            )

        await client.connect()
        self._context = AuthenticatedGraphQLContext(
            client=client,
            metadata=metadata,
            auth_manager=auth_manager,
        )
        return self._context

    async def close(self) -> None:
        """Close any connected client created by this bootstrapper."""

        if self._context is None:
            return

        await self._context.client.close()
        self._context = None

    def _resolve_auth_method(self) -> ResolvedAuthMethod:
        if self.auth_mode in {"api_key", "oidc"}:
            return self.auth_mode

        resolved_user = self.user or os.getenv("EVERGREEN_USER")
        resolved_api_key = self.api_key or os.getenv("EVERGREEN_API_KEY")
        if resolved_user and resolved_api_key:
            return "api_key"

        return "oidc"

    def _resolve_api_key_credentials(self) -> tuple[str, str]:
        user = self.user or os.getenv("EVERGREEN_USER")
        api_key = self.api_key or os.getenv("EVERGREEN_API_KEY")
        if user and api_key:
            return user, api_key

        raise AuthBootstrapError(
            "API key auth requires EVERGREEN_USER and EVERGREEN_API_KEY"
        )

    @staticmethod
    def _create_oidc_auth_manager() -> OIDCAuthManager:
        from evergreen_mcp.oidc_auth import OIDCAuthManager

        return OIDCAuthManager()


def graphql_client_context(**kwargs: Any) -> EvergreenGraphQLBootstrap:
    """Return an async context manager for authenticated GraphQL access."""

    return EvergreenGraphQLBootstrap(**kwargs)
