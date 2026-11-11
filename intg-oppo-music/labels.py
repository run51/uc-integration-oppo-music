"""Short texts the remote shows for an album: its format ("SACD 5.1/2.0", "Blu-ray 5.1"...) and the
info lines under covers and titles.

The remote draws these lines in Space Mono 22 px (13.4 px per character) and cuts what does not fit,
so each line is chosen among candidates, longest first: the first one that fits is kept, otherwise
the last one, ordered so that the format stays visible when the end is cut.
"""

SEP = " · "
LIST_WIDTH = 22  # subtitle of a media browser row (308 px); also the line under a cover
HEADER_WIDTH = 34  # line under the title of an album page (480 px)
PLAYER_WIDTH = 34  # second line of the player widget, under the cover

SOURCES = (("Blu-ray Audio", "Blu-ray"), ("DVD-Audio", "DVD-Audio"))
KNOWN_TAGS = {"SACD", "Blu-ray Audio", "DVD-Audio", "Quad", "Q8"}


def join(*parts) -> str:
    return SEP.join(str(p) for p in parts if p)


def first_fit(candidates, width: int) -> str:
    """First candidate that fits in `width` characters, else the last one."""
    candidates = [c for c in candidates if c]
    for candidate in candidates:
        if len(candidate) <= width:
            return candidate
    return candidates[-1] if candidates else ""


def channels(album: dict) -> str:
    """Channel layouts: both areas of a SACD ("5.1/2.0"), else the files' layout ("5.1")."""
    layouts = [x for x in album.get("layouts") or [] if x]
    if album.get("format") == "SACD":
        return "/".join(layouts)
    return album.get("channels") or "/".join(layouts)


def source(album: dict, long: bool = False) -> str:
    """Medium shown before the channels: SACD, Blu-ray (Audio), DVD-Audio, Quad, else FLAC or DSD."""
    tags = album.get("tags") or []
    if album.get("format") == "SACD":
        return "SACD"
    for name, short in SOURCES:
        if name in tags:
            return name if long else short
    if "Quad" in tags:
        return "Quad"
    return album.get("format") or ""


def format_label(album: dict, long: bool = False) -> str:
    return f"{source(album, long)} {channels(album)}".strip()


def extra_tags(album: dict) -> list[str]:
    """Other tags of the album folder worth showing, such as "2003 remix"."""
    return [t for t in album.get("tags") or [] if t not in KNOWN_TAGS and t != album.get("format")]


def year(album: dict) -> str:
    return str(album["year"]) if album.get("year") else ""


def artist_album_line(album: dict) -> str:
    """Subtitle of an album among its artist's albums: "1975 · SACD 5.1/2.0"."""
    return first_fit(
        [
            join(year(album), format_label(album, long=True)),
            join(year(album), format_label(album)),
            format_label(album),
        ],
        LIST_WIDTH,
    )


def album_line(album: dict) -> str:
    """Subtitle of an album in a list of several artists: "Genesis · SACD 5.1/2.0"."""
    artist = album.get("artist") or ""
    return first_fit([join(artist, format_label(album)), join(artist, source(album)), artist], LIST_WIDTH)


def header_line(album: dict) -> str:
    """Line under the title of the album page: "Pink Floyd · 1975 · SACD 5.1/2.0"."""
    artist = album.get("artist") or ""
    extra = ", ".join(extra_tags(album))
    return first_fit(
        [
            join(artist, year(album), format_label(album, long=True), extra),
            join(artist, year(album), format_label(album, long=True)),
            join(artist, year(album), format_label(album)),
            join(artist, format_label(album)),
            join(year(album), format_label(album)),
        ],
        HEADER_WIDTH,
    )


def playing_format(album: dict, sacd_priority: str | None = None, long: bool = True) -> str:
    """Format of what the player outputs. For a SACD, the area its "SACD priority" setting selects:
    "mch" (multichannel, the default), "stereo" or "cd"."""
    if album.get("format") != "SACD":
        return format_label(album, long)
    layouts = [x for x in album.get("layouts") or [] if x]
    multichannel = next((x for x in layouts if x != "2.0"), None)
    if sacd_priority == "cd":
        return "SACD, couche CD"
    if sacd_priority == "stereo" and "2.0" in layouts:
        return "SACD 2.0"
    if multichannel:
        return f"SACD {multichannel}"
    return format_label(album)


def player_line(album: dict, sacd_priority: str | None = None) -> str:
    """Second line of the player: "Pink Floyd · SACD 5.1"."""
    artist = album.get("artist") or ""
    short = playing_format(album, sacd_priority, long=False)
    return first_fit(
        [
            join(artist, playing_format(album, sacd_priority)),
            join(artist, short),
            join(short, artist),
        ],
        PLAYER_WIDTH,
    )
