"""OPPO Music player status (GET /api/status) as media player attributes for the remote, and the
signal the player reads ("DSD 5.1", "PCM 24/96 5.1") for the "Signal Oppo" sensor."""

from datetime import UTC, datetime

import labels
from ucapi.media_player import Attributes, MediaContentType, RepeatMode, States

# Transport states of the OPPO IP control protocol (#QPL) that mean "playing".
PLAYING = {"PLAY", "FFWD", "FREV", "SFWD", "SREV", "STEP", "SLOW"}
REPEAT = {"off": RepeatMode.OFF, "one": RepeatMode.ONE, "all": RepeatMode.ALL}
CLEARED = {
    Attributes.MEDIA_TITLE: "",
    Attributes.MEDIA_ARTIST: "",
    Attributes.MEDIA_ALBUM: "",
    Attributes.MEDIA_IMAGE_URL: "",
    Attributes.MEDIA_POSITION: 0,
    Attributes.MEDIA_DURATION: 0,
}


def ui_state(status: dict | None) -> States:
    if not status:
        return States.UNAVAILABLE  # the OPPO Music server does not answer
    if not status.get("reachable"):
        return States.OFF  # the server answers, the player does not (off or unplugged)
    state = status.get("state") or ""
    if state in PLAYING:
        return States.PLAYING
    if state == "PAUSE":
        return States.PAUSED
    if state == "OFF":
        return States.OFF
    return States.ON


def is_active(status: dict | None) -> bool:
    return ui_state(status) in (States.PLAYING, States.PAUSED)


def playing_album(status: dict | None, library) -> dict | None:
    """The library album being played: the one the server started, else the one the player reports."""
    if not status or library is None:
        return None
    ref = status.get("album") or {}
    if ref.get("id") and ref["id"] in library.albums:
        return library.albums[ref["id"]]
    info = status.get("info") or {}
    if info:
        title = info.get("album") or info.get("title")
        return library.match_album(info.get("artist"), title, info.get("kind"))
    return None


def current_track(status: dict, detail: dict | None) -> dict | None:
    """The track being played in an album's track list (GET /api/album/<id>)."""
    number = status.get("track")
    if not detail or not number:
        return None
    discs = detail.get("discs") or []
    if discs:
        disc = (status.get("now") or {}).get("disc")
        tracks = (discs[disc] if isinstance(disc, int) and 0 <= disc < len(discs) else discs[0]).get("tracks")
    else:
        tracks = detail.get("tracks")
    return next((t for t in tracks or [] if int(t.get("n") or 0) == number), None)


def attributes(
    status: dict | None, library=None, sacd_priority: str | None = None, now=None, album=None, detail=None
) -> dict:
    """Attributes for a status. `library` (a library.Library) may be None while it loads; `album` and
    `detail` (its track list) are the album being played when the driver resolved it."""
    state = ui_state(status)
    attrs = {Attributes.STATE: state, Attributes.MEDIA_TYPE: MediaContentType.MUSIC}
    repeat = (status or {}).get("repeat")
    attrs[Attributes.SHUFFLE] = repeat in ("shuffle", "random")
    attrs[Attributes.REPEAT] = REPEAT.get(repeat, RepeatMode.OFF)
    if state not in (States.PLAYING, States.PAUSED):
        attrs.update(CLEARED)
        return attrs

    if album is None:
        album = playing_album(status, library)
    ref = status.get("album") or {}
    info = status.get("info") or {}
    if album:
        track = current_track(status, detail) or {}
        title = status.get("title") or track.get("title") or album.get("title") or ""
        artist_line = labels.player_line(album, sacd_priority)
        album_title = album.get("title") or ""
        image = library.cover(album["id"], 600) if library is not None else ""
    else:
        # started elsewhere and not in the library (a disc in the tray): what the player reports
        title = status.get("title") or info.get("title") or ref.get("title") or ""
        artist_line = info.get("artist") or ref.get("artist") or ""
        album_title = info.get("album") or ref.get("title") or ""
        image = ""
    elapsed, remaining = status.get("elapsed"), status.get("remaining")
    attrs.update(
        {
            Attributes.MEDIA_TITLE: title,
            Attributes.MEDIA_ARTIST: artist_line,
            Attributes.MEDIA_ALBUM: album_title,
            Attributes.MEDIA_IMAGE_URL: image or "",
            Attributes.MEDIA_POSITION: int(elapsed or 0),
            Attributes.MEDIA_DURATION: int((elapsed or 0) + remaining) if remaining is not None else 0,
            Attributes.MEDIA_POSITION_UPDATED_AT: (now or datetime.now(UTC)).isoformat(),
        }
    )
    return attrs


def khz(rate) -> str:
    """96000 → "96", 44100 → "44.1"."""
    return f"{rate / 1000:g}"


def signal(status: dict | None, album=None, detail=None, sacd_priority: str | None = None) -> str:
    """What the player reads, as its front display shows it: "DSD 5.1" for the multichannel area of a
    SACD, "DSD 2.0" for its stereo area, "PCM 24/96 5.1" for FLAC files. Empty when nothing plays."""
    if not is_active(status):
        return ""
    if album:
        if album.get("format") == "SACD":
            if sacd_priority == "cd":
                return "PCM 2.0 (CD)"
            layouts = [x for x in album.get("layouts") or [] if x]
            multichannel = next((x for x in layouts if x != "2.0"), None)
            stereo = sacd_priority == "stereo" and "2.0" in layouts
            return f"DSD {'2.0' if stereo or not multichannel else multichannel}"
        track = current_track(status, detail) or next(iter((detail or {}).get("tracks") or []), {})
        rate, bits = track.get("rate"), track.get("bits")
        channels = track.get("channels") or album.get("channels") or ""
        if album.get("format") == "DSD" or (rate and rate >= 2822400):
            return f"DSD {channels}".strip()
        resolution = f"{bits}/{khz(rate)}" if bits and rate else ""
        return " ".join(p for p in ("PCM", resolution, channels) if p)
    kind = ((status or {}).get("info") or {}).get("kind") or ""
    return "DSD" if "DSD" in kind.upper() else kind
