"""HTTP client for the OPPO Music server (JSON API on port 8098). Standard library only: the calls
run in a worker thread so they never block the event loop."""

import asyncio
import json
import urllib.error
import urllib.request

from ucapi import StatusCodes


class OppoMusicError(Exception):
    """The OPPO Music server answered with an error ({"error": ...} and an HTTP status)."""

    def __init__(self, status: int, error: str):
        super().__init__(f"{status} {error}")
        self.status = status
        self.error = error

    def status_code(self) -> StatusCodes:
        if self.status == 404:
            return StatusCodes.NOT_FOUND
        if self.status == 400:
            return StatusCodes.BAD_REQUEST
        if self.status in (502, 503):
            return StatusCodes.SERVICE_UNAVAILABLE  # e.g. "oppo_unreachable"
        return StatusCodes.SERVER_ERROR


class OppoMusicClient:
    def __init__(self, server: str):
        self.server = server.rstrip("/")

    async def get(self, path: str, timeout: float = 10):
        return await asyncio.to_thread(self._request, "GET", path, None, timeout)

    async def post(self, path: str, body: dict, timeout: float = 10):
        return await asyncio.to_thread(self._request, "POST", path, body, timeout)

    def _request(self, method: str, path: str, body: dict | None, timeout: float):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        request = urllib.request.Request(self.server + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read() or b"null")
        except urllib.error.HTTPError as ex:
            try:
                error = json.loads(ex.read() or b"{}").get("error") or ex.reason
            except (ValueError, AttributeError):
                error = ex.reason
            raise OppoMusicError(ex.code, str(error)) from None
