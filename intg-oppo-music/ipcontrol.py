"""OPPO IP control (port 23), for the few commands the OPPO Music server does not offer, such as
Pure Audio. It goes through the oppo-multiplexer (the player accepts a single IP control
connection), one short connection per command like the other clients.

Pure Audio (#PUR) only toggles; its answer gives the new state ("OK ON" / "OK OFF"), so a discrete
"on" or "off" is a toggle followed, when the answer shows the wrong state, by a second toggle.
"""

import asyncio
import contextlib
import json
import logging
import re
import socket
import urllib.request

_LOG = logging.getLogger("ipcontrol")

STATE = re.compile(r"\bOK\s+(ON|OFF)\b")
UPDATE = re.compile(r"^U[A-Z0-9]{2}\b")  # unsolicited updates of the verbose mode ("UPL PLAY")


def parse_state(reply: str | None) -> bool | None:
    """True for "OK ON", False for "OK OFF", None otherwise (an error, or the player is busy)."""
    match = STATE.search(reply or "")
    return None if match is None else match.group(1) == "ON"


def split_address(address: str, default_port: int = 23) -> tuple[str, int]:
    host, sep, port = (address or "").strip().rpartition(":")
    if not sep:
        return address.strip(), default_port
    return host, int(port)


class IpControl:
    def __init__(self, address: str):
        self.host, self.port = split_address(address)

    def __str__(self) -> str:
        return f"{self.host}:{self.port}"

    async def command(self, code: str, timeout: float = 5.0) -> str:
        """Send "#CODE" and return the answer without its "@" ("OK ON", "QPW OK ON", "ER INVALID")."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), timeout)
        try:
            writer.write(f"#{code}\r".encode("ascii"))
            await writer.drain()
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise TimeoutError(f"#{code}: no answer")
                line = await asyncio.wait_for(reader.readuntil(b"\r"), remaining)
                text = line.decode("ascii", "replace").strip().lstrip("@").strip()
                if text and not UPDATE.match(text):
                    return text
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()


async def power_state(ipc: IpControl, timeout: float = 3.0) -> bool | None:
    """#QPW: True when the player is on, False in standby, None without an answer. The player
    answers #QPW even in standby, where its transport queries (#QPL, #QTK...) go unanswered."""
    try:
        return parse_state(await ipc.command("QPW", timeout))
    except (OSError, TimeoutError) as ex:
        _LOG.debug("#QPW: %s", ex)
        return None


async def set_pure_audio(
    ipc: IpControl,
    on: bool,
    wait_power: float = 0.0,
    retry_delay: float = 2.0,
    attempts: int = 4,
    timeout: float = 5.0,
) -> bool | None:
    """Turn Pure Audio on or off.

    Waits up to `wait_power` seconds for the player to be on (it is starting up when an activity
    begins). Returns True once the player confirmed the wanted state, False if the player stayed
    off (nothing done), None if it never confirmed.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_power
    while True:
        power = await power_state(ipc, timeout)
        if power:
            break
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(retry_delay)
    for _ in range(attempts):
        try:
            reply = await ipc.command("PUR", timeout)
        except (OSError, TimeoutError) as ex:
            _LOG.debug("#PUR: %s", ex)
            reply = None
        state = parse_state(reply)
        _LOG.debug("#PUR → %s", reply)
        if state is on:
            return True
        if state is None:
            await asyncio.sleep(retry_delay)  # refused while the player starts up: try again
        # otherwise it toggled the wrong way: the next toggle sets it right
    return None


def main_software_up(host: str, timeout: float = 2.0, port: int = 436) -> bool:
    """True when the player's HTTP port (436) accepts a connection, i.e. its main software runs. It is
    closed in standby. Checked on the player itself, not through the oppo-multiplexer."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def power_off(ipc: IpControl, timeout: float, interval: float = 2.0) -> bool:
    """#POF until #QPW says the player is off. Right after a Pure Audio switch the player answers #POF
    "OK OFF" and stays on (seen twice on 2026-11-11, #POF 0.8 s after #PUR), so the result is checked
    and the command sent again. True once off, False if still on after `timeout` seconds."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        try:
            _LOG.debug("#POF → %s", await ipc.command("POF", min(5.0, timeout)))
        except (OSError, TimeoutError) as ex:
            _LOG.debug("#POF: %s", ex)
        await asyncio.sleep(interval)
        if await power_state(ipc, 3.0) is False:
            return True
        if loop.time() >= deadline:
            return False


LOGIN_NOTICE = b"NOTIFY OREMOTE LOGIN"  # what the official app sends when it starts (UDP 7624)


def http_ready(host: str, timeout: float = 3.0) -> bool:
    """True when the player's HTTP interface (port 436) answers. It belongs to the player's main
    software: right after "power on" only the standby controller answers IP control, and what is set
    then (Pure Audio) is reset when the main software starts. The interface only opens once a control
    app has announced itself, hence the UDP notice first."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.sendto(LOGIN_NOTICE, (host, 7624))
        with urllib.request.urlopen(f"http://{host}:436/getmainfirmwareversion", timeout=timeout) as r:
            return bool(json.loads(r.read() or b"{}").get("success"))
    except (OSError, ValueError, AttributeError):
        return False


async def wait_until_started(host: str, timeout: float, interval: float = 2.0) -> bool:
    """Wait until the player has fully started (see http_ready). False if it did not within `timeout`."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if await asyncio.to_thread(http_ready, host):
            return True
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(interval)
