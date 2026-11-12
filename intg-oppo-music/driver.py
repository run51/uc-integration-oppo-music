#!/usr/bin/env python3
"""OPPO Music integration for the Unfolded Circle Remote Two / Remote 3.

One media player entity, "OPPO Music": the remote browses the OPPO Music library with it (artists,
albums, tracks, with their covers and formats), searches it, plays an album or a track, and shows
what the OPPO plays. Everything goes through the OPPO Music server, which indexes the music, serves
the covers and drives the OPPO UDP-203 / UDP-205.
"""

import asyncio
import contextlib
import json
import logging
import os
import socket
import time
import urllib.parse

import images
import status as player_status
import ucapi
from client import OppoMusicClient, OppoMusicError
from ipcontrol import IpControl, main_software_up, power_off, power_state, set_pure_audio, wait_until_started
from library import Library, play_request
from style import style_value
from ucapi import media_player as mp
from ucapi import sensor

_LOG = logging.getLogger("driver")

ENTITY_ID = "oppo_music"
SIGNAL_ID = "oppo_signal"  # sensor: what the player reads ("DSD 5.1", "PCM 24/96 5.1")
LIBRARY_TTL = 600  # s: the server rescans by itself; a new album shows up within 10 min
SACD_TTL = 600  # s: the "SACD priority" setting (multichannel / stereo) rarely changes
DETAIL_CACHE = 64  # album track lists kept in memory
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
PLAY_WAIT = 8  # s: an answer is sent to the remote by then even if the player is still loading
POLL_ACTIVE = 3  # s between status polls while playing or paused
POLL_IDLE = 10
POLL_OFF = 15  # the player is off: only its HTTP port is checked (see read_status)
POLL_UNREACHABLE = 60  # on, but its IP control does not answer: do not pile up queries
POLL_ERROR = 15
STATUS_TIMEOUT = 20
POWER_TIMEOUT = 3  # s for #QPW: answered within a few ms while the player is on or just off
ACTIVE = (mp.States.PLAYING, mp.States.PAUSED)

FEATURES = [
    mp.Features.PLAY_PAUSE,
    mp.Features.STOP,
    mp.Features.NEXT,
    mp.Features.PREVIOUS,
    mp.Features.SEEK,
    mp.Features.REPEAT,
    mp.Features.SHUFFLE,
    mp.Features.MEDIA_DURATION,
    mp.Features.MEDIA_POSITION,
    mp.Features.MEDIA_TITLE,
    mp.Features.MEDIA_ARTIST,
    mp.Features.MEDIA_ALBUM,
    mp.Features.MEDIA_IMAGE_URL,
    mp.Features.MEDIA_TYPE,
    mp.Features.PLAY_MEDIA,
    mp.Features.BROWSE_MEDIA,
    mp.Features.SEARCH_MEDIA,
    mp.Features.SEARCH_MEDIA_CLASSES,
]
REPEAT_KEYS = {"OFF": "repeat_off", "ALL": "repeat_all", "ONE": "repeat_one"}
# Simple commands, for activity sequences and buttons
PURE_AUDIO_ON = "PURE_AUDIO_ON"
PURE_AUDIO_OFF = "PURE_AUDIO_OFF"
OPPO_OFF = "OPPO_OFF"  # Pure Audio off, then the player off, checked: for the end of an activity
SIMPLE_COMMANDS = [PURE_AUDIO_ON, PURE_AUDIO_OFF, OPPO_OFF]
PURE_AUDIO_WAIT = 120  # s: at the start of an activity the player may still be starting up
PURE_AUDIO_OFF_TIMEOUT = 12
OPPO_OFF_TIMEOUT = 9  # s: the remote waited 8.2 s for a power-on; a following "off" step is the fallback
PURE_AUDIO_SETTLE = 5  # s after the player has started, before Pure Audio is set
PURE_AUDIO_FALLBACK_DELAY = 45  # s, when the player address is unknown and its start cannot be seen


IMAGE_PORT = 9310  # the Remote refuses 8000-9200 to custom integrations


def lan_address() -> str:
    """Address of the Remote on the local network (the covers are also shown by the web configurator)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))  # no packet is sent: only the route is looked up
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def normalize_server(value: str) -> str:
    """ "192.168.2.208:8098" → "http://192.168.2.208:8098" (no trailing slash)."""
    value = (value or "").strip().rstrip("/")
    if value and "://" not in value:
        value = "http://" + value
    return value


def default_ip_control(server: str) -> str:
    """The oppo-multiplexer usually runs on the same host as the OPPO Music server, port 23."""
    return f"{urllib.parse.urlsplit(server).hostname or ''}:23"


def page_bounds(paging) -> tuple[int, int]:
    page = max(1, int(getattr(paging, "page", 1) or 1))
    limit = min(MAX_LIMIT, max(1, int(getattr(paging, "limit", DEFAULT_LIMIT) or DEFAULT_LIMIT)))
    return page, limit


def poll_interval(state) -> int:
    if state in (mp.States.PLAYING, mp.States.PAUSED):
        return POLL_ACTIVE
    if state == mp.States.OFF:
        return POLL_OFF
    return POLL_IDLE


def truthy(value) -> bool:
    return value is True or str(value).lower() in ("true", "1", "on")


class OppoMusicPlayer(mp.MediaPlayer):
    def __init__(self, driver: "Driver"):
        super().__init__(
            ENTITY_ID,
            {"en": "OPPO Music", "fr": "OPPO Music"},
            FEATURES,
            {
                mp.Attributes.STATE: mp.States.UNKNOWN,
                mp.Attributes.SEARCH_MEDIA_CLASSES: ["artist", "album"],
            },
            device_class=mp.DeviceClasses.SPEAKER,
            options={mp.Options.SIMPLE_COMMANDS: SIMPLE_COMMANDS},
            cmd_handler=driver.on_command,
        )
        self._driver = driver

    async def browse(self, options):
        return await self._driver.browse(options)

    async def search(self, options):
        return await self._driver.search(options)


class Driver:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.api = ucapi.IntegrationAPI(loop)
        self.client: OppoMusicClient | None = None
        self.ip_control: IpControl | None = None
        self.oppo_host = ""
        self.last_signal: str | None = None
        self.sensor_font_size, self.sensor_color = 0, ""
        self.background: set[asyncio.Task] = set()
        self.library: Library | None = None
        self.images: images.ImageCache | None = None
        self.library_at = 0.0
        self.library_lock = asyncio.Lock()
        self.details: dict[str, dict] = {}
        self.sacd_priority: str | None = None
        self.sacd_at = 0.0
        self.poll_task: asyncio.Task | None = None
        self.refresh = asyncio.Event()
        self.last: dict = {}

    # ------------------------------------------------------------- configuration

    def config_file(self) -> str:
        return os.path.join(self.api.config_dir_path, "config.json")

    def load_config(self) -> dict | None:
        try:
            with open(self.config_file(), encoding="utf-8") as file:
                return json.load(file)
        except (OSError, ValueError):
            return None

    def save_config(
        self,
        server: str,
        ip_control: str = "",
        oppo_host: str = "",
        sensor_font_size: int = 0,
        sensor_color: str = "",
    ) -> None:
        os.makedirs(os.path.dirname(self.config_file()) or ".", exist_ok=True)
        config: dict = {"server": server}
        if ip_control:
            config["ip_control"] = ip_control
        if oppo_host:
            config["oppo_host"] = oppo_host
        if sensor_font_size:
            config["sensor_font_size"] = sensor_font_size
        if sensor_color:
            config["sensor_color"] = sensor_color
        with open(self.config_file(), "w", encoding="utf-8") as file:
            json.dump(config, file)

    def configure(
        self,
        server: str,
        ip_control: str = "",
        oppo_host: str = "",
        sensor_font_size: int = 0,
        sensor_color: str = "",
    ) -> None:
        self.sensor_font_size, self.sensor_color = sensor_font_size, sensor_color.strip()
        self.last_signal = None  # resend the signal with the new style
        self.client = OppoMusicClient(server)
        self.ip_control = IpControl(ip_control or default_ip_control(server))
        self.oppo_host = oppo_host.strip()
        self.library, self.library_at = None, 0.0
        self.details.clear()
        if self.images is None:
            port = int(os.getenv("OPPO_MUSIC_IMAGE_PORT", str(IMAGE_PORT)))
            self.images = images.ImageCache(os.path.join(self.api.config_dir_path, "images"))
            self.images.base = f"http://{lan_address()}:{port}"
            try:
                images.serve(self.images, port)
            except OSError as ex:  # covers then come straight from the server
                _LOG.warning("Image cache not served on port %d: %s", port, ex)
                self.images.base = ""
        self.last = {}
        if not self.api.available_entities.contains(ENTITY_ID):
            self.api.available_entities.add(OppoMusicPlayer(self))
        if not self.api.available_entities.contains(SIGNAL_ID):
            self.api.available_entities.add(
                sensor.Sensor(
                    SIGNAL_ID,
                    {"en": "OPPO signal", "fr": "Signal Oppo"},
                    [],
                    {sensor.Attributes.STATE: sensor.States.ON, sensor.Attributes.VALUE: ""},
                    device_class=sensor.DeviceClasses.CUSTOM,
                )
            )
        _LOG.info(
            "OPPO Music server: %s, IP control: %s, player: %s",
            server,
            self.ip_control,
            self.oppo_host or "?",
        )

    async def setup_handler(self, msg: ucapi.SetupDriver) -> ucapi.SetupAction:
        if isinstance(msg, ucapi.DriverSetupRequest):
            server = normalize_server(msg.setup_data.get("server", ""))
            if not server:
                return ucapi.SetupError(ucapi.IntegrationSetupError.NOT_FOUND)
            try:
                data = await OppoMusicClient(server).get("/api/library", timeout=20)
            except OppoMusicError as ex:
                _LOG.warning("Setup: %s answered %s", server, ex)
                return ucapi.SetupError(ucapi.IntegrationSetupError.NOT_FOUND)
            except (OSError, ValueError) as ex:
                _LOG.warning("Setup: %s unreachable: %s", server, ex)
                return ucapi.SetupError(ucapi.IntegrationSetupError.CONNECTION_REFUSED)
            if not isinstance(data, dict) or "albums" not in data:
                return ucapi.SetupError(ucapi.IntegrationSetupError.NOT_FOUND)
            ip_control = (msg.setup_data.get("ip_control") or "").strip()
            oppo_host = (msg.setup_data.get("oppo_host") or "").strip()
            try:
                font_size = int(float(msg.setup_data.get("sensor_font_size") or 0))
            except (TypeError, ValueError):
                font_size = 0
            color = (msg.setup_data.get("sensor_color") or "").strip()
            self.save_config(server, ip_control, oppo_host, font_size, color)
            self.configure(server, ip_control, oppo_host, font_size, color)
            self.library, self.library_at = self.new_library(data, server), time.time()
            _LOG.info(
                "Setup done: %d artists, %d albums",
                len(self.library.artists),
                len(self.library.albums),
            )
            return ucapi.SetupComplete()
        if isinstance(msg, ucapi.AbortDriverSetup):
            _LOG.info("Setup aborted: %s", msg.error)
        return ucapi.SetupError()

    # ------------------------------------------------------------------- library

    def new_library(self, data: dict, server: str) -> Library:
        """Library whose covers go through the image cache; the covers not cached yet are queued."""
        library = Library(data, server, self.images.url_for if self.images and self.images.base else None)
        if self.images and self.images.base:
            queued = self.images.prefetch(library.cover_urls())
            if queued:
                _LOG.info("Image cache: %d covers queued", queued)
        return library

    async def ensure_library(self) -> Library:
        if self.client is None:
            raise OppoMusicError(503, "not_configured")
        async with self.library_lock:
            if self.library is None or time.time() - self.library_at > LIBRARY_TTL:
                try:
                    data = await self.client.get("/api/library", timeout=20)
                    self.library = self.new_library(data, self.client.server)
                    self.details.clear()
                except (OppoMusicError, OSError, ValueError):
                    if self.library is None:
                        raise
                    _LOG.warning("Library refresh failed, keeping the previous one", exc_info=True)
                self.library_at = time.time()
        return self.library

    async def album_detail(self, album_id: str) -> dict:
        if album_id in self.details:
            return self.details[album_id]
        detail = await self.client.get(f"/api/album/{urllib.parse.quote(album_id)}", timeout=20)
        if len(self.details) >= DETAIL_CACHE:
            self.details.pop(next(iter(self.details)))
        self.details[album_id] = detail
        return detail

    async def browse(self, options: mp.BrowseOptions):
        media_id = options.media_id or "root"
        try:
            library = await self.ensure_library()
            detail = await self.album_detail(media_id[6:]) if media_id.startswith("album:") else None
            container, items = library.browse(media_id, detail)
        except KeyError:
            return ucapi.StatusCodes.NOT_FOUND
        except OppoMusicError as ex:
            _LOG.warning("Browse %s: %s", media_id, ex)
            return ex.status_code()
        except (OSError, ValueError) as ex:
            _LOG.warning("Browse %s: server unreachable: %s", media_id, ex)
            return ucapi.StatusCodes.SERVICE_UNAVAILABLE
        page, limit = page_bounds(options.paging)
        container.items = items[(page - 1) * limit : page * limit]
        return mp.BrowseResults(
            media=container, pagination=ucapi.Pagination(page=page, limit=limit, count=len(items))
        )

    async def search(self, options: mp.SearchOptions):
        try:
            library = await self.ensure_library()
        except OppoMusicError as ex:
            return ex.status_code()
        except (OSError, ValueError):
            return ucapi.StatusCodes.SERVICE_UNAVAILABLE
        classes = options.filter.media_classes if options.filter else None
        items = library.search(options.query, classes)
        page, limit = page_bounds(options.paging)
        return mp.SearchResults(
            media=items[(page - 1) * limit : page * limit],
            pagination=ucapi.Pagination(page=page, limit=limit, count=len(items)),
        )

    # ------------------------------------------------------------------ commands

    async def key(self, name: str) -> None:
        await self.client.post("/api/key", {"key": name}, timeout=10)

    async def on_command(self, entity, cmd_id: str, params: dict | None, websocket=None):
        params = params or {}
        if self.client is None:
            return ucapi.StatusCodes.SERVICE_UNAVAILABLE
        _LOG.info("Command %s %s", cmd_id, params or "")
        try:
            if cmd_id == mp.Commands.PLAY_PAUSE:
                await self.key("toggle")
            elif cmd_id == mp.Commands.STOP:
                await self.key("stop")
            elif cmd_id == mp.Commands.NEXT:
                await self.key("next")
            elif cmd_id == mp.Commands.PREVIOUS:
                await self.key("prev")
            elif cmd_id == mp.Commands.SEEK:
                position = float(params.get("media_position", 0))
                await self.client.post("/api/seek", {"position": position}, timeout=10)
            elif cmd_id == mp.Commands.REPEAT:
                mode = str(params.get("repeat", "OFF")).upper()
                await self.key(REPEAT_KEYS.get(mode, "repeat_off"))
            elif cmd_id == mp.Commands.SHUFFLE:
                await self.key("shuffle" if truthy(params.get("shuffle")) else "repeat_off")
            elif cmd_id == mp.Commands.PLAY_MEDIA:
                return await self.play_media(str(params.get("media_id") or ""))
            elif cmd_id == PURE_AUDIO_ON:
                # answered at once: the player is often still starting up when an activity begins
                self.run_in_background(self.pure_audio(True, PURE_AUDIO_WAIT))
                self.refresh.set()  # the player is on by now: show it
                return ucapi.StatusCodes.OK
            elif cmd_id == PURE_AUDIO_OFF:
                # waited for, so that a following "power off" step comes after it
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.pure_audio(False, 0), PURE_AUDIO_OFF_TIMEOUT)
                return ucapi.StatusCodes.OK
            elif cmd_id == OPPO_OFF:
                # waited for, and stopped at the timeout: nothing may turn the player off later, when
                # another activity could be starting it
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.oppo_off(), OPPO_OFF_TIMEOUT)
                self.refresh.set()
                return ucapi.StatusCodes.OK
            else:
                return ucapi.StatusCodes.NOT_IMPLEMENTED
        except OppoMusicError as ex:
            _LOG.warning("Command %s: %s", cmd_id, ex)
            return ex.status_code()
        except ValueError:
            return ucapi.StatusCodes.BAD_REQUEST
        except OSError as ex:
            _LOG.warning("Command %s: server unreachable: %s", cmd_id, ex)
            return ucapi.StatusCodes.SERVICE_UNAVAILABLE
        self.refresh.set()
        return ucapi.StatusCodes.OK

    async def play_media(self, media_id: str):
        body = play_request(media_id)
        if body is None:
            return ucapi.StatusCodes.BAD_REQUEST
        # Starting a disc image takes the OPPO 10-20 s: answer the remote by PLAY_WAIT, let it finish.
        task = asyncio.ensure_future(self.client.post("/api/play", body, timeout=90))
        done, _ = await asyncio.wait({task}, timeout=PLAY_WAIT)
        if task in done:
            try:
                task.result()
            except OppoMusicError as ex:
                _LOG.warning("Play %s: %s", media_id, ex)
                return ex.status_code()
            except OSError as ex:
                _LOG.warning("Play %s: server unreachable: %s", media_id, ex)
                return ucapi.StatusCodes.SERVICE_UNAVAILABLE
        else:
            task.add_done_callback(lambda t: self.after_background_play(media_id, t))
        self.refresh.set()
        return ucapi.StatusCodes.OK

    def run_in_background(self, coro) -> None:
        task = self.loop.create_task(coro)
        self.background.add(task)
        task.add_done_callback(self.background.discard)

    async def pure_audio(self, on: bool, wait_power: float) -> None:
        if self.ip_control is None:
            return
        if on:
            # Right after "power on" the player confirms everything, then resets Pure Audio when its
            # main software starts: wait for that first.
            if self.oppo_host:
                if not await wait_until_started(self.oppo_host, wait_power):
                    _LOG.warning("Pure Audio on: the player did not start within %d s", wait_power)
                    return
                self.refresh.set()  # its HTTP port is open now: show the player on
                await asyncio.sleep(PURE_AUDIO_SETTLE)
            else:
                await asyncio.sleep(PURE_AUDIO_FALLBACK_DELAY)
        result = await set_pure_audio(self.ip_control, on, wait_power)
        wanted = "on" if on else "off"
        if result:
            _LOG.info("Pure Audio %s", wanted)
        elif result is False:
            _LOG.info("Pure Audio %s: the player is off, nothing done", wanted)
        else:
            _LOG.warning("Pure Audio %s: the player did not confirm", wanted)

    async def oppo_off(self) -> None:
        """Pure Audio off, then the player off. After a Pure Audio switch the player acknowledges
        "power off" and may stay on: the result is checked and the command sent again."""
        if self.ip_control is None:
            return
        power = await power_state(self.ip_control, POWER_TIMEOUT)
        if power is not True:
            _LOG.info("OPPO off: %s", "already off" if power is False else "no answer, nothing done")
            return
        started = self.loop.time()
        if await set_pure_audio(self.ip_control, False, 0) is None:
            _LOG.warning("OPPO off: Pure Audio off not confirmed")
        try:
            off = await power_off(self.ip_control, OPPO_OFF_TIMEOUT)
        except asyncio.CancelledError:
            _LOG.warning("OPPO off: still on after %.1f s, left to the next step", self.loop.time() - started)
            raise
        if off:
            _LOG.info("OPPO off after %.1f s", self.loop.time() - started)
        else:
            _LOG.warning("OPPO off: still on after %.1f s", self.loop.time() - started)

    def after_background_play(self, media_id: str, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        if task.exception() is not None:
            _LOG.warning("Play %s failed: %s", media_id, task.exception())
        self.refresh.set()

    # ------------------------------------------------------------------- polling

    def start_polling(self) -> None:
        if self.client is not None and (self.poll_task is None or self.poll_task.done()):
            self.poll_task = self.loop.create_task(self.poll_loop())

    def stop_polling(self) -> None:
        if self.poll_task is not None:
            self.poll_task.cancel()
            self.poll_task = None

    async def update_sacd_priority(self, album: dict | None) -> None:
        if not album or album.get("format") != "SACD":
            return
        if self.sacd_priority and time.time() - self.sacd_at < SACD_TTL:
            return
        self.sacd_at = time.time()
        try:
            self.sacd_priority = (await self.client.get("/api/sacd", timeout=15)).get("priority")
        except (OppoMusicError, OSError, ValueError, AttributeError) as ex:
            _LOG.debug("SACD priority unavailable: %s", ex)

    async def read_status(self) -> dict:
        """The player status. GET /api/status only while the player is really on: in standby the OPPO
        answers none of the server's IP control queries, and the oppo-multiplexer waits 10 s for each
        (50 s for one status). The remote's own Oppo driver waited behind them, and its "power on"
        failed at the start of an activity.

        In standby the HTTP port (436) is closed: nothing is asked. For a few seconds after "power off"
        it is still open; the player then answers #QPW at once ("OK OFF") but not the transport queries,
        so #QPW is asked first (seen 2026-11-11: #QPW answered in 4 ms, #QPL held the multiplexer 10 s
        and the next activity's power-on got through with 0.6 s to spare)."""
        if self.oppo_host and not await asyncio.to_thread(main_software_up, self.oppo_host):
            return {"reachable": True, "state": "OFF"}
        if self.ip_control is not None:
            power = await power_state(self.ip_control, POWER_TIMEOUT)
            if power is None and self.last.get(mp.Attributes.STATE) in ACTIVE:
                power = await power_state(self.ip_control, POWER_TIMEOUT)  # one missed answer
            if power is False:
                return {"reachable": True, "state": "OFF"}
            if power is None:
                return {"reachable": False, "state": None}
        return await self.client.get("/api/status", timeout=STATUS_TIMEOUT)

    async def poll_loop(self) -> None:
        while True:
            interval = POLL_ERROR
            try:
                status = await self.read_status()
                library = self.library
                if library is None or time.time() - self.library_at > LIBRARY_TTL:
                    with contextlib.suppress(OppoMusicError, OSError, ValueError):
                        library = await self.ensure_library()
                album = player_status.playing_album(status, library)
                detail = None
                if album is not None and player_status.is_active(status):
                    await self.update_sacd_priority(album)
                    with contextlib.suppress(OppoMusicError, OSError, ValueError):
                        detail = await self.album_detail(album["id"])
                attrs = player_status.attributes(
                    status, library, self.sacd_priority, album=album, detail=detail
                )
                self.push(attrs)
                self.push_signal(player_status.signal(status, album, detail, self.sacd_priority))
                interval = poll_interval(attrs[mp.Attributes.STATE])
                if not status.get("reachable"):
                    interval = POLL_UNREACHABLE
            except asyncio.CancelledError:
                raise
            except (OppoMusicError, OSError, ValueError) as ex:
                _LOG.debug("Status unavailable: %s", ex)
                self.push(player_status.attributes(None))
                self.push_signal("")
            self.refresh.clear()
            try:
                await asyncio.wait_for(self.refresh.wait(), timeout=interval)
                await asyncio.sleep(0.8)  # after a command: let the player apply it
            except TimeoutError:
                pass

    def push(self, attrs: dict) -> None:
        """Send the attributes that changed. The position time stamp only goes with a new position."""
        stamp = mp.Attributes.MEDIA_POSITION_UPDATED_AT
        changed = {k: v for k, v in attrs.items() if k != stamp and self.last.get(k) != v}
        if not changed:
            return
        if mp.Attributes.MEDIA_POSITION in changed and stamp in attrs:
            changed[stamp] = attrs[stamp]
        self.last.update(changed)
        self.api.available_entities.update_attributes(ENTITY_ID, changed)
        self.api.configured_entities.update_attributes(ENTITY_ID, changed)

    def push_signal(self, value: str) -> None:
        if value == self.last_signal:
            return
        self.last_signal = value
        styled = style_value(value, self.sensor_font_size, self.sensor_color)
        attrs = {sensor.Attributes.STATE: sensor.States.ON, sensor.Attributes.VALUE: styled}
        self.api.available_entities.update_attributes(SIGNAL_ID, attrs)
        self.api.configured_entities.update_attributes(SIGNAL_ID, attrs)

    # -------------------------------------------------------------------- events

    def register_events(self) -> None:
        api = self.api

        @api.listens_to(ucapi.Events.CONNECT)
        async def on_connect(websocket=None) -> None:
            await api.set_device_state(ucapi.DeviceStates.CONNECTED)
            self.start_polling()

        @api.listens_to(ucapi.Events.DISCONNECT)
        async def on_disconnect(websocket=None) -> None:
            self.stop_polling()

        @api.listens_to(ucapi.Events.ENTER_STANDBY)
        async def on_enter_standby(websocket=None) -> None:
            self.stop_polling()

        @api.listens_to(ucapi.Events.EXIT_STANDBY)
        async def on_exit_standby(websocket=None) -> None:
            self.start_polling()
            self.refresh.set()

        @api.listens_to(ucapi.Events.SUBSCRIBE_ENTITIES)
        async def on_subscribe(entity_ids, websocket=None) -> None:
            self.last, self.last_signal = {}, None  # send everything again to the new subscriber
            self.start_polling()
            self.refresh.set()


async def main() -> None:
    logging.basicConfig(
        format="%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    level = os.getenv("UC_LOG_LEVEL", "INFO").upper()
    for name in ("driver", "ipcontrol", "ucapi.api", "ucapi.entities"):
        logging.getLogger(name).setLevel(level)

    driver = Driver(asyncio.get_running_loop())
    driver.register_events()
    config = driver.load_config()
    if config and config.get("server"):
        driver.configure(
            config["server"],
            config.get("ip_control", ""),
            config.get("oppo_host", ""),
            config.get("sensor_font_size", 0),
            config.get("sensor_color", ""),
        )
    await driver.api.init("driver.json", driver.setup_handler)
    await asyncio.Event().wait()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
