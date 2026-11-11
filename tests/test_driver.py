import asyncio
from types import SimpleNamespace

import driver as drv
import pytest
import ucapi
from client import OppoMusicError
from ucapi.media_player import BrowseOptions, Commands, SearchOptions


class FakeClient:
    """Stands in for the OPPO Music server."""

    def __init__(self, library_data, detail=None, play_delay=0.0, play_error=None):
        self.server = "http://192.168.2.208:8098"
        self.library_data = library_data
        self.detail = detail or {"discs": [], "tracks": []}
        self.play_delay = play_delay
        self.play_error = play_error
        self.posts = []
        self.gets = []

    async def get(self, path, timeout=10):
        self.gets.append(path)
        if path == "/api/library":
            return self.library_data
        if path.startswith("/api/album/"):
            return self.detail
        if path == "/api/status":
            return {"reachable": True, "state": "HOME MENU"}
        if path == "/api/sacd":
            return {"priority": "mch"}
        raise OppoMusicError(404, "not_found")

    async def post(self, path, body, timeout=10):
        self.posts.append((path, body))
        if path == "/api/play":
            await asyncio.sleep(self.play_delay)
            if self.play_error:
                raise self.play_error
        return {"ok": True}


@pytest.fixture
def driver(library_data, wywh_detail):
    d = drv.Driver(asyncio.new_event_loop())
    d.client = FakeClient(library_data, wywh_detail)
    return d


def test_helpers():
    assert drv.normalize_server(" 192.168.2.208:8098/ ") == "http://192.168.2.208:8098"
    assert drv.normalize_server("https://music.local") == "https://music.local"
    assert drv.normalize_server("") == ""
    assert drv.page_bounds(SimpleNamespace(page=0, limit=500)) == (1, drv.MAX_LIMIT)
    assert drv.page_bounds(ucapi.Paging(page=3, limit=20)) == (3, 20)
    assert drv.truthy(True) and drv.truthy("true") and not drv.truthy(False) and not drv.truthy(None)
    assert drv.poll_interval("PLAYING") == drv.POLL_ACTIVE == drv.poll_interval("PAUSED")
    assert drv.poll_interval("OFF") == drv.POLL_OFF
    assert drv.poll_interval("ON") == drv.POLL_IDLE
    assert drv.default_ip_control("http://192.168.2.208:8098") == "192.168.2.208:23"


async def test_pure_audio_commands(driver, monkeypatch):
    calls = []

    async def fake_pure_audio(on, wait_power):
        calls.append((on, wait_power))

    monkeypatch.setattr(driver, "pure_audio", fake_pure_audio)
    driver.loop = asyncio.get_running_loop()
    assert await driver.on_command(None, drv.PURE_AUDIO_ON, None) == ucapi.StatusCodes.OK
    assert await driver.on_command(None, drv.PURE_AUDIO_OFF, None) == ucapi.StatusCodes.OK
    await asyncio.sleep(0)  # let the background task run
    assert sorted(calls) == [(False, 0), (True, drv.PURE_AUDIO_WAIT)]
    entity = drv.OppoMusicPlayer(driver)
    assert entity.options["simple_commands"] == ["PURE_AUDIO_ON", "PURE_AUDIO_OFF", "OPPO_OFF"]


async def test_browse_pages(driver):
    result = await driver.browse(BrowseOptions(media_id="artists", paging=ucapi.Paging(page=2, limit=3)))
    assert result.pagination.count == 4
    assert [i.title for i in result.media.items] == ["Pink Floyd"]
    page = await driver.browse(BrowseOptions(media_id="album:wywh"))
    assert [i.media_id for i in page.media.items] == ["track:wywh:0:1", "track:wywh:0:2"]
    assert await driver.browse(BrowseOptions(media_id="artist:nope")) == ucapi.StatusCodes.NOT_FOUND


async def test_browse_without_server():
    d = drv.Driver(asyncio.get_running_loop())
    assert await d.browse(BrowseOptions(media_id=None)) == ucapi.StatusCodes.SERVICE_UNAVAILABLE


async def test_search(driver):
    result = await driver.search(SearchOptions(query="floyd", paging=ucapi.Paging(page=1, limit=2)))
    assert result.pagination.count == 4  # the artist and its three albums
    assert [i.media_id for i in result.media] == ["artist:pf", "album:ahm"]


async def test_commands(driver):
    ok = ucapi.StatusCodes.OK
    assert await driver.on_command(None, Commands.PLAY_PAUSE, None) == ok
    assert await driver.on_command(None, Commands.NEXT, None) == ok
    assert await driver.on_command(None, Commands.SEEK, {"media_position": 61}) == ok
    assert await driver.on_command(None, Commands.REPEAT, {"repeat": "ONE"}) == ok
    assert await driver.on_command(None, Commands.SHUFFLE, {"shuffle": True}) == ok
    assert await driver.on_command(None, Commands.SHUFFLE, {"shuffle": False}) == ok
    assert driver.client.posts == [
        ("/api/key", {"key": "toggle"}),
        ("/api/key", {"key": "next"}),
        ("/api/seek", {"position": 61.0}),
        ("/api/key", {"key": "repeat_one"}),
        ("/api/key", {"key": "shuffle"}),
        ("/api/key", {"key": "repeat_off"}),
    ]
    assert await driver.on_command(None, Commands.VOLUME_UP, None) == ucapi.StatusCodes.NOT_IMPLEMENTED


async def test_play_media(driver, library_data):
    ok = ucapi.StatusCodes.OK
    assert await driver.on_command(None, Commands.PLAY_MEDIA, {"media_id": "track:wywh:0:2"}) == ok
    assert driver.client.posts[-1] == ("/api/play", {"album": "wywh", "disc": 0, "track": 2})
    assert (
        await driver.on_command(None, Commands.PLAY_MEDIA, {"media_id": "artist:pf"})
        == ucapi.StatusCodes.BAD_REQUEST
    )
    driver.client.play_error = OppoMusicError(404, "not_found")
    assert (
        await driver.on_command(None, Commands.PLAY_MEDIA, {"media_id": "album:x"})
        == ucapi.StatusCodes.NOT_FOUND
    )


async def test_slow_play_answers_early(driver, monkeypatch):
    monkeypatch.setattr(drv, "PLAY_WAIT", 0.05)
    driver.client.play_delay = 0.3
    started = asyncio.get_running_loop().time()
    assert await driver.play_media("album:wywh") == ucapi.StatusCodes.OK
    assert asyncio.get_running_loop().time() - started < 0.25
    await asyncio.sleep(0.35)  # the request finishes in the background


def test_push_sends_only_changes(driver):
    sent = []
    driver.api.configured_entities.update_attributes = lambda eid, attrs: sent.append(dict(attrs))
    driver.api.available_entities.update_attributes = lambda eid, attrs: True
    stamp = "media_position_updated_at"
    driver.push({"state": "PLAYING", "media_position": 1, stamp: "t1"})
    driver.push({"state": "PLAYING", "media_position": 1, stamp: "t2"})  # nothing new
    driver.push({"state": "PLAYING", "media_position": 4, stamp: "t3"})
    assert sent == [
        {"state": "PLAYING", "media_position": 1, stamp: "t1"},
        {"media_position": 4, stamp: "t3"},
    ]


async def test_pure_audio_waits_for_the_player_to_start(driver, monkeypatch):
    import ipcontrol  # noqa: F401

    events = []

    async def fake_started(host, timeout):
        events.append(("started?", host))
        return True

    async def fake_set(ipc, on, wait_power):
        events.append(("set", on))
        return True

    async def no_sleep(seconds):
        events.append(("sleep", seconds))

    monkeypatch.setattr(drv, "wait_until_started", fake_started)
    monkeypatch.setattr(drv, "set_pure_audio", fake_set)
    monkeypatch.setattr(drv.asyncio, "sleep", no_sleep)
    driver.configure("http://192.168.2.208:8098", "", "192.168.2.195")
    await driver.pure_audio(True, 120)
    assert events == [("started?", "192.168.2.195"), ("sleep", drv.PURE_AUDIO_SETTLE), ("set", True)]
    events.clear()
    await driver.pure_audio(False, 0)  # off: no need to wait
    assert events == [("set", False)]


def test_signal_sensor(driver):
    sent = []
    driver.configure("http://192.168.2.208:8098")
    assert driver.api.available_entities.contains(drv.SIGNAL_ID)
    driver.api.configured_entities.update_attributes = lambda eid, attrs: sent.append((eid, dict(attrs)))
    driver.push_signal("DSD 5.1")
    driver.push_signal("DSD 5.1")
    driver.push_signal("")
    assert [a["value"] for _, a in sent] == ["DSD 5.1", ""]


async def test_status_asks_the_server_only_when_the_player_is_on(driver, monkeypatch):
    """In standby (port 436 closed) or just turned off (#QPW "OK OFF") the OPPO answers none of the
    server's queries: they would block the multiplexer."""
    up, power = [], []
    monkeypatch.setattr(drv, "main_software_up", lambda host: up.pop(0))

    async def fake_power(ipc, timeout):
        return power.pop(0)

    monkeypatch.setattr(drv, "power_state", fake_power)
    driver.oppo_host, driver.ip_control = "192.168.2.195", object()
    up[:], power[:] = [False], []  # standby: nothing asked, not even #QPW
    assert await driver.read_status() == {"reachable": True, "state": "OFF"}
    up[:], power[:] = [True], [False]  # just turned off, port 436 still open
    assert await driver.read_status() == {"reachable": True, "state": "OFF"}
    assert driver.client.gets == []
    up[:], power[:] = [True], [True]
    assert await driver.read_status() == {"reachable": True, "state": "HOME MENU"}
    assert driver.client.gets == ["/api/status"]
    up[:], power[:] = [True], [None]  # on but its IP control does not answer
    assert await driver.read_status() == {"reachable": False, "state": None}
    driver.last = {"state": "PLAYING"}
    up[:], power[:] = [True], [None, True]  # one missed answer while playing is asked again
    assert await driver.read_status() == {"reachable": True, "state": "HOME MENU"}
    assert up == [] and power == [] and driver.client.gets == ["/api/status", "/api/status"]
    driver.oppo_host, driver.ip_control = "", None  # addresses unknown: the server alone
    assert await driver.read_status() == {"reachable": True, "state": "HOME MENU"}


def test_main_software_up():
    import socket

    from ipcontrol import main_software_up

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert main_software_up("127.0.0.1", 0.5, port) is True
    assert main_software_up("127.0.0.1", 0.5, port) is False  # closed, as in standby


async def test_oppo_off(driver, monkeypatch):
    events, power = [], []

    async def fake_power(ipc, timeout):
        return power.pop(0)

    async def fake_set(ipc, on, wait_power):
        events.append(("pure audio", on))
        return True

    async def fake_off(ipc, timeout):
        events.append(("off", timeout))
        return True

    monkeypatch.setattr(drv, "power_state", fake_power)
    monkeypatch.setattr(drv, "set_pure_audio", fake_set)
    monkeypatch.setattr(drv, "power_off", fake_off)
    driver.loop = asyncio.get_running_loop()
    driver.ip_control = object()
    power[:] = [True]
    assert await driver.on_command(None, drv.OPPO_OFF, None) == ucapi.StatusCodes.OK
    assert events == [("pure audio", False), ("off", drv.OPPO_OFF_TIMEOUT)]
    events.clear()
    power[:] = [False]  # already off: nothing sent
    assert await driver.on_command(None, drv.OPPO_OFF, None) == ucapi.StatusCodes.OK
    assert events == []
