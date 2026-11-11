from datetime import UTC, datetime

import status
from conftest import SERVER
from ucapi.media_player import Attributes as A
from ucapi.media_player import RepeatMode, States

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)


def playing(**extra):
    st = {
        "reachable": True,
        "state": "PLAY",
        "track": 1,
        "tracks": 5,
        "elapsed": 222,
        "remaining": 594,
        "title": "Shine On You Crazy Diamond (Parts I - V)",
        "repeat": "off",
        "now": {"album": "wywh", "disc": 0},
        "album": {"id": "wywh", "title": "Wish You Were Here", "artist": "Pink Floyd", "cover": True},
    }
    st.update(extra)
    return st


def test_server_down_and_player_off():
    attrs = status.attributes(None)
    assert attrs[A.STATE] == States.UNAVAILABLE
    assert attrs[A.MEDIA_TITLE] == "" and attrs[A.MEDIA_IMAGE_URL] == ""
    assert status.attributes({"reachable": False, "state": None})[A.STATE] == States.OFF
    assert status.attributes({"reachable": True, "state": "OFF"})[A.STATE] == States.OFF


def test_playing_a_sacd(library):
    attrs = status.attributes(playing(), library, "mch", now=NOW)
    assert attrs[A.STATE] == States.PLAYING
    assert attrs[A.MEDIA_TITLE] == "Shine On You Crazy Diamond (Parts I - V)"
    assert attrs[A.MEDIA_ARTIST] == "Pink Floyd · SACD 5.1"
    assert attrs[A.MEDIA_ALBUM] == "Wish You Were Here"
    assert attrs[A.MEDIA_IMAGE_URL] == f"{SERVER}/api/cover/wywh?s=600"
    assert attrs[A.MEDIA_POSITION] == 222
    assert attrs[A.MEDIA_DURATION] == 816
    assert attrs[A.MEDIA_POSITION_UPDATED_AT] == NOW.isoformat()
    assert attrs[A.REPEAT] == RepeatMode.OFF and attrs[A.SHUFFLE] is False
    assert status.attributes(playing(), library, "stereo")[A.MEDIA_ARTIST] == "Pink Floyd · SACD 2.0"


def test_paused_and_repeat_modes(library):
    attrs = status.attributes(playing(state="PAUSE", repeat="shuffle"), library)
    assert attrs[A.STATE] == States.PAUSED
    assert attrs[A.SHUFFLE] is True and attrs[A.REPEAT] == RepeatMode.OFF
    assert status.attributes(playing(repeat="one"), library)[A.REPEAT] == RepeatMode.ONE
    assert status.attributes(playing(repeat="all"), library)[A.REPEAT] == RepeatMode.ALL


def test_idle_player_clears_the_media(library):
    attrs = status.attributes({"reachable": True, "state": "HOME MENU", "now": None, "album": None}, library)
    assert attrs[A.STATE] == States.ON
    assert attrs[A.MEDIA_TITLE] == "" and attrs[A.MEDIA_DURATION] == 0


def test_playback_started_elsewhere(library):
    st = {
        "reachable": True,
        "state": "PLAY",
        "elapsed": 10,
        "remaining": None,
        "title": None,
        "now": None,
        "album": None,
        "info": {"title": "Track 3", "artist": "Some Band", "album": "Live"},
    }
    attrs = status.attributes(st, library)
    assert attrs[A.MEDIA_TITLE] == "Track 3"
    assert attrs[A.MEDIA_ARTIST] == "Some Band"
    assert attrs[A.MEDIA_ALBUM] == "Live"
    assert attrs[A.MEDIA_IMAGE_URL] == ""
    assert attrs[A.MEDIA_DURATION] == 0


def test_library_not_loaded_yet():
    attrs = status.attributes(playing(), None)
    assert attrs[A.MEDIA_TITLE] == "Shine On You Crazy Diamond (Parts I - V)"
    assert attrs[A.MEDIA_ARTIST] == "Pink Floyd"
    assert attrs[A.MEDIA_IMAGE_URL] == ""


def test_server_lost_track_of_the_album(library, wywh_detail):
    st = {
        "reachable": True,
        "state": "PLAY",
        "track": 2,
        "tracks": 5,
        "elapsed": 52,
        "remaining": 180,
        "title": None,
        "now": None,
        "album": None,
        "info": {
            "title": "Wish You Were Here",
            "album": "Wish You Were Here",
            "artist": "Pink Floyd",
            "kind": "SACD DSD",
        },
    }
    album = status.playing_album(st, library)
    assert album["id"] == "wywh"
    attrs = status.attributes(st, library, "mch", album=album, detail=wywh_detail)
    assert attrs[A.MEDIA_TITLE] == "Welcome To The Machine"
    assert attrs[A.MEDIA_ARTIST] == "Pink Floyd · SACD 5.1"
    assert attrs[A.MEDIA_IMAGE_URL] == f"{SERVER}/api/cover/wywh?s=600"


def test_signal(library, wywh_detail):
    wywh = library.albums["wywh"]
    assert status.signal(playing(), wywh, wywh_detail, "mch") == "DSD 5.1"
    assert status.signal(playing(), wywh, wywh_detail, None) == "DSD 5.1"
    assert status.signal(playing(), wywh, wywh_detail, "stereo") == "DSD 2.0"
    assert status.signal(playing(), wywh, wywh_detail, "cd") == "PCM 2.0 (CD)"
    abbey = library.albums["abbey"]
    files = {
        "discs": [],
        "tracks": [
            {"n": 1, "rate": 96000, "bits": 24, "channels": "5.1"},
            {"n": 2, "rate": 44100, "bits": 16, "channels": "2.0"},
        ],
    }
    assert status.signal(playing(track=1), abbey, files) == "PCM 24/96 5.1"
    assert status.signal(playing(track=2), abbey, files) == "PCM 16/44.1 2.0"
    assert status.signal(playing(track=None), abbey, None) == "PCM 5.1"
    dsf = {"format": "DSD", "channels": "2.0", "layouts": ["2.0"], "tags": []}
    assert status.signal(playing(), dsf, {"discs": [], "tracks": [{"n": 1, "rate": 2822400}]}) == "DSD 2.0"
    tray = {"reachable": True, "state": "PLAY", "info": {"kind": "SACD DSD"}}
    assert status.signal(tray) == "DSD"
    assert status.signal({"reachable": True, "state": "HOME MENU"}, wywh) == ""
