from __future__ import annotations
import json
from typing import Any, Literal
import aiohttp
import asyncio
import logging

from .const import BASE_API

_LOGGER = logging.getLogger(__name__)

class KitchenOSClient:
    """Async client using Home Assistant's shared aiohttp session."""

    def __init__(self, session, access_token: str, device_id: str, module_idx: int = 0):
        self._session = session
        self._token = access_token
        self._device_id = device_id
        self._module_idx = module_idx

        # Common headers for GETs (capabilities/sessions)
        self._headers_get = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/x.default+json;version=2",
        }
        # POST to /cooking/execute — some stacks dislike the Accept version header here
        self._headers_post = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def get_appliance_capabilities(self, model_id: str) -> dict:
        url = f"{BASE_API}/appliances/{model_id}"
        _LOGGER.debug("GET %s", url)
        async with self._session.get(url, headers=self._headers_get, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            text = await resp.text()
            _LOGGER.debug("GET %s -> %s %s\n%s", url, resp.status, resp.reason, text[:1000])
            resp.raise_for_status()
            try:
                return json.loads(text)
            except Exception:
                return {}

    async def list_sessions(self) -> dict:
        url = f"{BASE_API}/cooking/sessions/"
        _LOGGER.debug("GET %s", url)
        async with self._session.get(url, headers=self._headers_get, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            text = await resp.text()
            _LOGGER.debug("GET %s -> %s %s\n%s", url, resp.status, resp.reason, text[:1000])
            resp.raise_for_status()
            try:
                return json.loads(text)
            except Exception:
                return {}

    async def execute(
        self,
        command: Literal["kitchenos:Command:Start", "kitchenos:Command:Update", "kitchenos:Command:Cancel"],
        capability: dict | None = None,
        composite_capabilities: list[dict] | None = None,
    ) -> dict:
        """POST /cooking/execute with clearer error reporting."""
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

        try:
            async with self._session.post(
                url,
                headers=self._headers_post,
                data=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                text = await resp.text()
                _LOGGER.debug("POST %s -> %s %s\n%s", url, resp.status, resp.reason, text[:2000])

                # Cloud often returns 202 on success
                if resp.status in (200, 201, 202, 204):
                    try:
                        return json.loads(text) if text else {"status": resp.status}
                    except Exception:
                        return {"status": resp.status, "text": text[:2000]}

                # Bubble a readable error
                raise RuntimeError(f"/cooking/execute {resp.status} {resp.reason}: {text}")

        except asyncio.TimeoutError as e:
            _LOGGER.error("Timeout calling %s: %s", url, e)
            raise
        except aiohttp.ClientResponseError as e:
            _LOGGER.error("HTTP error calling %s: %s", url, e)
            raise
        except Exception as e:
            _LOGGER.error("Unexpected error calling %s: %s", url, e)
            raise

