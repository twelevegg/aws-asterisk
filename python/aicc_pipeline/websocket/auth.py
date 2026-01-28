"""
WebSocket Authentication for outbound connections.

Generates JWT tokens for authenticating with external WebSocket servers.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger("aicc.ws_auth")

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    logger.warning("PyJWT not installed, WebSocket auth disabled. pip install PyJWT")


class WebSocketAuth:
    """
    JWT-based authentication for outbound WebSocket connections.

    Generates tokens that external servers can validate to verify
    our identity as an authorized AICC pipeline client.
    """

    def __init__(
        self,
        secret_key: str,
        client_id: str,
        algorithm: str = "HS256",
        token_ttl_hours: float = 1.0,
    ):
        """
        Initialize WebSocket auth.

        Args:
            secret_key: Shared secret for JWT signing
            client_id: Unique identifier for this client
            algorithm: JWT algorithm (default: HS256)
            token_ttl_hours: Token time-to-live in hours
        """
        if not JWT_AVAILABLE:
            raise ImportError("PyJWT required for WebSocket auth. pip install PyJWT")

        self.secret_key = secret_key
        self.client_id = client_id
        self.algorithm = algorithm
        self.token_ttl = timedelta(hours=token_ttl_hours)

        self._cached_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    def generate_token(
        self,
        permissions: Optional[List[str]] = None,
        extra_claims: Optional[Dict] = None,
    ) -> str:
        """
        Generate a JWT token for outbound WebSocket authentication.

        Args:
            permissions: List of permissions (default: ['send_transcripts'])
            extra_claims: Additional claims to include in token

        Returns:
            JWT token string
        """
        now = datetime.utcnow()
        expires_at = now + self.token_ttl

        payload = {
            'client_id': self.client_id,
            'permissions': permissions or ['send_transcripts'],
            'iat': now,
            'exp': expires_at,
            'nbf': now,  # Not valid before
        }

        if extra_claims:
            payload.update(extra_claims)

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        # Cache the token
        self._cached_token = token
        self._token_expires_at = expires_at

        logger.debug(f"Generated JWT token for client {self.client_id}, expires at {expires_at}")

        return token

    def get_token(self, refresh_margin_minutes: float = 5.0) -> str:
        """
        Get a valid token, refreshing if needed.

        Args:
            refresh_margin_minutes: Refresh token this many minutes before expiry

        Returns:
            Valid JWT token
        """
        now = datetime.utcnow()
        margin = timedelta(minutes=refresh_margin_minutes)

        # Check if cached token is still valid
        if (
            self._cached_token
            and self._token_expires_at
            and now + margin < self._token_expires_at
        ):
            return self._cached_token

        # Generate new token
        return self.generate_token()

    def get_auth_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers for WebSocket authentication.

        Returns:
            Dict with Authorization header
        """
        token = self.get_token()
        return {
            'Authorization': f'Bearer {token}'
        }

    @staticmethod
    def from_env() -> Optional["WebSocketAuth"]:
        """
        Create WebSocketAuth from environment variables.

        Required env vars:
        - WS_AUTH_SECRET_KEY: JWT signing secret
        - WS_AUTH_CLIENT_ID: Client identifier

        Optional env vars:
        - WS_AUTH_ALGORITHM: JWT algorithm (default: HS256)
        - WS_AUTH_TOKEN_TTL_HOURS: Token TTL (default: 1.0)

        Returns:
            WebSocketAuth instance or None if env vars not set
        """
        import os

        secret_key = os.environ.get('WS_AUTH_SECRET_KEY')
        client_id = os.environ.get('WS_AUTH_CLIENT_ID')

        if not secret_key or not client_id:
            logger.debug("WS_AUTH_SECRET_KEY or WS_AUTH_CLIENT_ID not set, auth disabled")
            return None

        algorithm = os.environ.get('WS_AUTH_ALGORITHM', 'HS256')
        token_ttl = float(os.environ.get('WS_AUTH_TOKEN_TTL_HOURS', '1.0'))

        return WebSocketAuth(
            secret_key=secret_key,
            client_id=client_id,
            algorithm=algorithm,
            token_ttl_hours=token_ttl,
        )
