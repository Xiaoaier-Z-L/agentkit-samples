"""AgentKit Memory adapter injected through Runtime associations."""

from __future__ import annotations

import hashlib
import os
import time

import requests


def build_platform_memory(app_name: str):
    """Return a VeADK mem0 backend or None when no platform binding exists."""
    endpoint = os.getenv("DATABASE_MEM0_BASE_URL", "").rstrip("/")
    api_key = os.getenv("DATABASE_MEM0_API_KEY", "")
    if not endpoint or not api_key:
        return None
    from veadk.memory import LongTermMemory
    from veadk.memory.long_term_memory_backends.base_backend import (
        BaseLongTermMemoryBackend,
    )

    class AgentKitMem0Backend(BaseLongTermMemoryBackend):
        """Small Mem0 REST adapter; avoids shipping an unused local vector DB."""

        def precheck_index_naming(self) -> bool:
            """Validate the runtime-selected index before VeADK starts using it.

            AgentKit injects the Mem0 binding at runtime.  The platform accepts
            the application name as the index namespace, so no remote call is
            needed here; this hook fulfils the VeADK backend contract.
            """
            return bool(self.index and self.index.strip())

        def _headers(self) -> dict[str, str]:
            return {
                "Authorization": f"Token {api_key}",
                "Mem0-User-ID": hashlib.md5(api_key.encode()).hexdigest(),
                "Content-Type": "application/json",
            }

        def save_memory(self, user_id: str, event_strings: list[str], **kwargs) -> bool:
            del kwargs
            messages = [
                {"role": "user", "content": event_string}
                for event_string in event_strings
                if event_string.strip()
            ]
            if not messages:
                return True
            # Mem0 accepts a message list.  One batch prevents a session's
            # individual events from exhausting the component's write quota.
            for attempt in range(3):
                response = requests.post(
                    f"{endpoint}/v1/memories/",
                    headers=self._headers(),
                    json={
                        "messages": messages,
                        "user_id": user_id,
                        "output_format": "v1.1",
                        "async_mode": True,
                        "version": "v2",
                    },
                    timeout=30,
                )
                if getattr(response, "status_code", None) == 429 and attempt < 2:
                    retry_after = getattr(response, "headers", {}).get("Retry-After", "")
                    try:
                        delay = min(float(retry_after), 2.0) if retry_after else 0.25 * (2**attempt)
                    except ValueError:
                        delay = 0.25 * (2**attempt)
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                return True
            return True

        def search_memory(
            self,
            query: str,
            top_k: int,
            user_id: str,
            **kwargs,
        ) -> list[str]:
            del kwargs
            response = requests.post(
                f"{endpoint}/v1/memories/search/",
                headers=self._headers(),
                json={
                    "query": query,
                    "user_id": user_id,
                    "output_format": "v1.1",
                    "top_k": top_k,
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            results = payload if isinstance(payload, list) else payload.get("results", [])
            return [str(item["memory"]) for item in results if item.get("memory")]

    return LongTermMemory(backend=AgentKitMem0Backend(index=app_name), app_name=app_name, top_k=3)
