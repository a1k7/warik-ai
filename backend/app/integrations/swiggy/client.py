"""Minimal MCP Streamable HTTP client for Swiggy.

The caller supplies a user-scoped OAuth bearer token. Never put a user's
Swiggy token in a global setting or share it across Warik accounts.
"""

import json
from typing import Any

import httpx


class SwiggyMCPError(RuntimeError):
    pass


class SwiggyMCPClient:
    PROTOCOL_VERSION = "2025-03-26"

    def __init__(
        self,
        endpoint: str,
        access_token: str,
        timeout_seconds: float = 20.0,
    ):
        if not access_token or not access_token.strip():
            raise SwiggyMCPError("Swiggy OAuth authorization is required.")

        self.endpoint = endpoint
        self.access_token = access_token.strip()
        self.timeout_seconds = timeout_seconds
        self.session_id: str | None = None
        self.request_id = 0

    def _headers(self, initialized: bool = False) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if initialized:
            headers["MCP-Protocol-Version"] = self.PROTOCOL_VERSION
        if self.session_id:
            headers["MCP-Session-Id"] = self.session_id
        return headers

    def _next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    @staticmethod
    def _decode_response(response: httpx.Response) -> dict[str, Any]:
        if response.status_code >= 400:
            detail = response.text[:1000]
            raise SwiggyMCPError(
                f"Swiggy MCP HTTP {response.status_code}: {detail}"
            )

        if response.status_code == 202 or not response.content:
            return {}

        content_type = response.headers.get("content-type", "").lower()

        if "text/event-stream" in content_type:
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    raw = line[5:].strip()
                    if raw and raw != "[DONE]":
                        try:
                            value = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(value, dict):
                            return value
            raise SwiggyMCPError("Swiggy MCP returned no JSON-RPC result.")

        try:
            value = response.json()
        except ValueError as exc:
            raise SwiggyMCPError("Swiggy MCP returned invalid JSON.") from exc

        if not isinstance(value, dict):
            raise SwiggyMCPError("Swiggy MCP returned an invalid response.")
        return value

    async def _post(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        initialized: bool = False,
    ) -> tuple[dict[str, Any], httpx.Response]:
        response = await client.post(
            self.endpoint,
            json=payload,
            headers=self._headers(initialized=initialized),
        )
        new_session = response.headers.get("MCP-Session-Id")
        if new_session:
            self.session_id = new_session
        return self._decode_response(response), response

    @staticmethod
    def _result_or_raise(envelope: dict[str, Any]) -> dict[str, Any]:
        if envelope.get("error"):
            error = envelope["error"]
            message = error.get("message", "Unknown JSON-RPC error")
            raise SwiggyMCPError(f"Swiggy MCP error: {message}")

        result = envelope.get("result")
        if not isinstance(result, dict):
            raise SwiggyMCPError("Swiggy MCP response did not contain a result.")

        if result.get("isError"):
            raise SwiggyMCPError(
                SwiggyMCPClient._error_message(result)
            )
        return result

    @staticmethod
    def _error_message(result: dict[str, Any]) -> str:
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            error = structured.get("error")
            if isinstance(error, dict):
                return str(error.get("message", "Tool call failed"))
        for block in result.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                return str(block.get("text", "Tool call failed"))[:1000]
        return "Swiggy MCP tool call failed."

    @staticmethod
    def read_tool_data(result: dict[str, Any]) -> dict[str, Any]:
        """Prefer structuredContent; parse JSON content only as fallback."""
        structured = result.get("structuredContent")
        if isinstance(structured, dict) and structured:
            data = structured
        else:
            text_block = next(
                (
                    block.get("text")
                    for block in result.get("content", [])
                    if isinstance(block, dict)
                    and block.get("type") == "text"
                    and isinstance(block.get("text"), str)
                ),
                None,
            )
            if not text_block:
                raise SwiggyMCPError(
                    "Swiggy MCP response contained no structured data."
                )
            try:
                envelope = json.loads(text_block)
            except json.JSONDecodeError as exc:
                raise SwiggyMCPError(
                    "Swiggy MCP returned text instead of a JSON data envelope."
                ) from exc
            if not isinstance(envelope, dict):
                raise SwiggyMCPError("Invalid Swiggy MCP data envelope.")
            if envelope.get("success") is False:
                error = envelope.get("error") or {}
                raise SwiggyMCPError(
                    str(error.get("message", envelope.get("message", "Tool failed")))
                )
            nested = envelope.get("data")
            data = dict(nested) if isinstance(nested, dict) else {}
            data.update(
                {
                    key: value
                    for key, value in envelope.items()
                    if key not in {"data", "success", "message", "error"}
                }
            )

        if data.get("success") is False:
            error = data.get("error") or {}
            raise SwiggyMCPError(
                str(error.get("message", "Swiggy tool call failed."))
            )
        return data

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=False,
        ) as client:
            initialize = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "Warik AI",
                        "version": "1.0.0",
                    },
                },
            }
            init_envelope, _ = await self._post(client, initialize)
            self._result_or_raise(init_envelope)

            notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
            await self._post(client, notification, initialized=True)

            call = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            }
            envelope, _ = await self._post(
                client,
                call,
                initialized=True,
            )
            result = self._result_or_raise(envelope)
            return self.read_tool_data(result)
