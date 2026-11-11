import asyncio

from ipcontrol import IpControl, parse_state, power_state, set_pure_audio, split_address


class FakeOppo:
    """A player on a local TCP port: power state, Pure Audio toggle, answers refused while busy."""

    def __init__(self, power=True, pure=False, busy=0, verbose=False):
        self.power, self.pure, self.busy, self.verbose = power, pure, busy, verbose
        self.received = []

    async def handle(self, reader, writer):
        code = (await reader.readuntil(b"\r")).decode().strip().lstrip("#")
        self.received.append(code)
        if self.verbose:
            writer.write(b"@UPL PLAY\r")
        if code == "QPW":
            if self.power is None:  # standby: the connection opens, nothing answers
                await asyncio.sleep(1)
                writer.close()
                return
            reply = "@QPW OK ON" if self.power else "@QPW OK OFF"
        elif self.busy:
            self.busy -= 1
            reply = "@ER INVALID"
        else:
            self.pure = not self.pure
            reply = "@OK ON" if self.pure else "@OK OFF"
        writer.write((reply + "\r").encode())
        await writer.drain()
        writer.close()

    async def start(self):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        port = self.server.sockets[0].getsockname()[1]
        return IpControl(f"127.0.0.1:{port}")

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()


async def run(oppo, on, **kwargs):
    ipc = await oppo.start()
    try:
        return await set_pure_audio(ipc, on, retry_delay=0.01, **kwargs)
    finally:
        await oppo.stop()


def test_parse_and_address():
    assert parse_state("OK ON") is True
    assert parse_state("QPW OK OFF") is False
    assert parse_state("ER INVALID") is None
    assert parse_state(None) is None
    assert split_address("192.168.2.208:23") == ("192.168.2.208", 23)
    assert split_address("oppo") == ("oppo", 23)


async def test_turns_pure_audio_on():
    oppo = FakeOppo(pure=False)
    assert await run(oppo, True) is True
    assert oppo.pure is True and oppo.received == ["QPW", "PUR"]


async def test_already_on_stays_on():
    oppo = FakeOppo(pure=True)
    assert await run(oppo, True) is True
    assert oppo.pure is True and oppo.received == ["QPW", "PUR", "PUR"]


async def test_turns_it_off():
    oppo = FakeOppo(pure=True)
    assert await run(oppo, False) is True
    assert oppo.pure is False


async def test_retries_while_the_player_starts_up():
    oppo = FakeOppo(pure=False, busy=2, verbose=True)
    assert await run(oppo, True) is True
    assert oppo.pure is True and oppo.received == ["QPW", "PUR", "PUR", "PUR"]


async def test_player_off_or_silent():
    oppo = FakeOppo(power=False)
    assert await run(oppo, True) is False
    assert oppo.received == ["QPW"]
    silent = FakeOppo(power=None)
    assert await run(silent, False, timeout=0.1) is False


async def test_waits_for_the_player_to_start():
    oppo = FakeOppo(power=False)

    async def power_on_later():
        await asyncio.sleep(0.05)
        oppo.power = True

    task = asyncio.ensure_future(power_on_later())
    assert await run(oppo, True, wait_power=2) is True
    await task
    assert oppo.pure is True and oppo.received[-1] == "PUR"


async def test_power_state():
    for power, expected in ((True, True), (False, False), (None, None)):
        oppo = FakeOppo(power=power, verbose=True)
        ipc = await oppo.start()
        try:
            assert await power_state(ipc, timeout=0.2) is expected
        finally:
            await oppo.stop()
        assert oppo.received == ["QPW"]


async def test_power_off_is_checked_and_sent_again():
    """The player acknowledges #POF and stays on right after a Pure Audio switch."""
    from ipcontrol import power_off

    received, state = [], {"on": True, "ignored": 2}

    async def handle(reader, writer):
        code = (await reader.readuntil(b"\r")).decode().strip().lstrip("#")
        received.append(code)
        if code == "POF":
            if state["ignored"]:
                state["ignored"] -= 1  # acknowledged, not done
            else:
                state["on"] = False
            reply = "@POF OK OFF"
        else:
            reply = "@QPW OK ON" if state["on"] else "@QPW OK OFF"
        writer.write((reply + "\r").encode())
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    ipc = IpControl(f"127.0.0.1:{server.sockets[0].getsockname()[1]}")
    try:
        assert await power_off(ipc, timeout=2, interval=0.01) is True
        assert received == ["POF", "QPW", "POF", "QPW", "POF", "QPW"]
        state.update(on=True, ignored=10**6)  # never done: gives up at the timeout
        assert await power_off(ipc, timeout=0.1, interval=0.02) is False
    finally:
        server.close()
        await server.wait_closed()
