from __future__ import annotations
import json
from typing import Any, Literal, Optional
import aiohttp
import asyncio
import logging
from time import monotonic

from .const import BASE_API

_LOGGER = logging.getLogger(__name__)

class CognitoAuthError(RuntimeError):
    pass

class CognitoTokenManager:
    """
    Cognito token manager that supports:
      - Initial USER_PASSWORD_AUTH login
      - REFRESH_TOKEN_AUTH using RefreshToken
      - Proactive refresh a little before AccessToken expiry
    """
    def __init__(self, session: aiohttp.ClientSession, *, username: str, password: str, client_id: str, region: str):
        self._session = session
        self._username = username
        self._password = password
        self._client_id = client_id
        self._region = region

        self._access_token: Optional[str] = None
        self._id_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._expires_at: float = 0.0  # monotonic() timestamp when access token expires
        self._lock = asyncio.Lock()

    # ----------------- Public getters -----------------
    async def get_access_token(self) -> str:
        """Return a valid (non-expired) AccessToken, refreshing if needed."""
        async with self._lock:
            await self._ensure_fresh_locked()
            if not self._access_token:
                raise CognitoAuthError("No AccessToken available after refresh/login.")
            return self._access_token

    async def get_id_token(self) -> Optional[str]:
        """Return the latest IdToken (may be None on some flows)."""
        async with self._lock:
            await self._ensure_fresh_locked()
            return self._id_token

    # ----------------- Core flows -----------------
    async def _ensure_fresh_locked(self):
        now = monotonic()
        # refresh 90 seconds before expiry as a safety margin
        if self._access_token and now < (self._expires_at - 90):
            return  # still fresh

        if self._refresh_token:
            try:
                await self._refresh_locked()
                return
            except Exception as e:
                _LOGGER.warning("Refresh failed, will attempt full login: %s", e)

        await self._login_locked()

    async def login(self) -> None:
        """Public login (outside lock) for places like config_flow."""
        async with self._lock:
            await self._login_locked()

    async def _login_locked(self) -> None:
        """USER_PASSWORD_AUTH to get Access/Id/Refresh tokens."""
        url = f"https://cognito-idp.{self._region}.amazonaws.com/"
        headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            "Accept-Charset": "UTF-8",
            "Accept": "*/*",
            "User-Agent": "Instantbrands/20749 CFNetwork/3826.600.41 Darwin/24.6.0",
        }
        body = {
            "ClientId": self._client_id,
            "AuthFlow": "USER_PASSWORD_AUTH",
            "AuthParameters": {
                "USERNAME": self._username,
                "PASSWORD": self._password
            }
        }
        _LOGGER.debug("Cognito login POST %s", url)
        async with self._session.post(url, headers=headers, data=json.dumps(body)) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise CognitoAuthError(f"Cognito login failed: {resp.status} {resp.reason} – {text[:500]}")
        self._parse_auth_result(text, source="login")

    async def _refresh_locked(self) -> None:
        """REFRESH_TOKEN_AUTH to get new Access/Id tokens using stored RefreshToken."""
        if not self._refresh_token:
            raise CognitoAuthError("No RefreshToken available to refresh.")
        url = f"https://cognito-idp.{self._region}.amazonaws.com/"
        headers = {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            "Accept-Charset": "UTF-8",
            "Accept": "*/*",
            "User-Agent": "Instantbrands/20749 CFNetwork/3826.600.41 Darwin/24.6.0",
        }
        body = {
            "ClientId": self._client_id,
            "AuthFlow": "REFRESH_TOKEN_AUTH",
            "AuthParameters": {
                "REFRESH_TOKEN": self._refresh_token
            }
        }
        _LOGGER.debug("Cognito refresh POST %s", url)
        async with self._session.post(url, headers=headers, data=json.dumps(body)) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise CognitoAuthError(f"Cognito refresh failed: {resp.status} {resp.reason} – {text[:500]}")
        self._parse_auth_result(text, source="refresh")

    def _parse_auth_result(self, text: str, *, source: str) -> None:
        try:
            data = json.loads(text)
            ar = data["AuthenticationResult"]
            access = ar.get("AccessToken")
            idt = ar.get("IdToken")
            # On refresh, Cognito may omit RefreshToken; keep the old one
            refresh = ar.get("RefreshToken") or self._refresh_token
            expires_in = ar.get("ExpiresIn", 3600)

            self._access_token = access
            self._id_token = idt
            self._refresh_token = refresh
            self._expires_at = monotonic() + int(expires_in)

            _LOGGER.debug(
                "Cognito %s OK; access=%s id=%s refresh=%s expires_in=%ss",
                source, bool(access), bool(idt), bool(refresh), expires_in
            )
        except Exception as e:
            raise CognitoAuthError(f"Cognito {source} parse error: {e}; body={text[:500]}")



class KitchenOSClient:
    """Async API client using CognitoTokenManager."""

    def __init__(self, session: aiohttp.ClientSession, token_mgr: CognitoTokenManager, device_id: str, module_idx: int = 0):
        self._session = session
        self._tm = token_mgr
        self._device_id = device_id
        self._module_idx = module_idx

    async def _auth_headers_get(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/x.default+json;version=2",
        }

    async def _auth_headers_post(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "User-Agent": "Instantbrands/20749 CFNetwork/3826.600.41 Darwin/24.6.0",
        }

    # ---------- User profile (device discovery) ----------
    async def get_user_profile(self) -> dict:
        url = f"{BASE_API}/user/"
        access = await self._tm.get_access_token()

        async def _once(tok: str) -> tuple[int, str, str]:
            headers = await self._auth_headers_get(tok)
            _LOGGER.debug("GET %s with AccessToken", url)
            async with self._session.get(url, headers=headers) as resp:
                text = await resp.text()
                _LOGGER.debug("GET %s -> %s %s\n%s", url, resp.status, resp.reason, text[:1000])
                return resp.status, resp.reason, text

        status, reason, text = await _once(access)
        if status in (401, 403):
            # Try with IdToken (some backends prefer it)
            idt = await self._tm.get_id_token()
            if idt:
                _LOGGER.debug("GET /user/ retrying with IdToken")
                headers = await self._auth_headers_get(idt)
                async with self._session.get(url, headers=headers) as resp:
                    text = await resp.text()
                    _LOGGER.debug("GET %s (IdToken) -> %s %s\n%s", url, resp.status, resp.reason, text[:1000])
                    status, reason = resp.status, resp.reason

        if status >= 400:
            raise RuntimeError(f"/user/ {status} {reason}: {text[:500]}")

        try:
            return json.loads(text)
        except Exception:
            return {}

    # ---------- Execute (commands) ----------
    async def execute(
        self,
        command: Literal["kitchenos:Command:Start", "kitchenos:Command:Update", "kitchenos:Command:Cancel"],
        capability: dict | None = None,
        composite_capabilities: list[dict] | None = None,
    ) -> dict:
        url = f"{BASE_API}/cooking/execute"
        body: dict[str, Any] = {
            "appliance_module_idx": self._module_idx,
            "device_id": self._device_id,
            "command": command,
            "composite_capabilities": composite_capabilities or [],
        }
        if capability is not None:
            body["capability"] = capability

        payload = json.dumps(body, separators=(",", ":"))
        _LOGGER.debug("POST %s\n%s", url, payload)

        async def _once(token: str) -> tuple[int, str, str]:
            headers = await self._auth_headers_post(token)
            async with self._session.post(url, headers=headers, data=payload) as resp:
                text = await resp.text()
                _LOGGER.debug("POST %s -> %s %s\n%s", url, resp.status, resp.reason, text[:2000])
                return resp.status, resp.reason, text

        # Try ID token first (mobile app does this), then Access token, then refresh+retry
        idt = await self._tm.get_id_token()
        if idt:
            status, reason, text = await _once(idt)
            if status in (200, 201, 202, 204):
                try:
                    return json.loads(text) if text else {"status": status}
                except Exception:
                    return {"status": status, "text": text[:2000]}
            if status not in (401, 403):
                raise RuntimeError(f"/cooking/execute {status} {reason}: {text[:500]}")

        # fall back to AccessToken
        access = await self._tm.get_access_token()
        status, reason, text = await _once(access)
        if status in (200, 201, 202, 204):
            try:
                return json.loads(text) if text else {"status": status}
            except Exception:
                return {"status": status, "text": text[:2000]}

        # auth error → refresh (will use REFRESH_TOKEN) then retry ID→Access
        if status in (401, 403):
            _LOGGER.warning("%s from /cooking/execute; refreshing tokens then retrying", status)
            await self._tm.login()  # refresh/login path
            idt = await self._tm.get_id_token()
            if idt:
                status, reason, text = await _once(idt)
                if status in (200, 201, 202, 204):
                    try:
                        return json.loads(text) if text else {"status": status}
                    except Exception:
                        return {"status": status, "text": text[:2000]}
            access = await self._tm.get_access_token()
            status, reason, text = await _once(access)

        # final error
        raise RuntimeError(f"/cooking/execute {status} {reason}: {text[:500]}")

    async def close(self) -> None:
        """Close the client and clean up resources."""
        _LOGGER.debug("Closing KitchenOSClient")
        # Close the token manager
        if self._tm:
            await self._tm.close()
        # The session is managed by Home Assistant, so we don't close it
        # Just clean up any internal state if needed
        self._tm = None
        _LOGGER.debug("KitchenOSClient closed")
