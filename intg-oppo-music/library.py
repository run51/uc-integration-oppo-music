"""The OPPO Music library as media browser items for the remote.

No I/O here: the driver fetches the library (GET /api/library) and an album's tracks
(GET /api/album/<id>) from the OPPO Music server and hands them over.

Media ids:
  root                      first screen: Artistes, Albums, Ajouts récents, Par format
  artists / albums / recent lists
  formats, format:<key>     albums by medium (SACD, Blu-ray Audio...)
  artist:<id>               an artist's albums, by year
  album:<id>                an album page (container) with its tracks
  track:<album>:<disc>:<n>  a track of disc image <disc> (0-based), or of the audio files ("f")
"""

import re
import unicodedata

import labels
from ucapi.media_player import BrowseMediaItem, MediaClass, MediaContentType

ROOT = "root"
RECENT_COUNT = 60
ICONS = {
    "artists": "icon://uc:users",
    "albums": "icon://uc:album-collection",
    "recent": "icon://uc:clock-rotate-left",
    "formats": "icon://uc:layer-group",
    "format": "icon://uc:compact-disc",
}
SOURCE_TAGS = {"Blu-ray Audio", "DVD-Audio", "Quad"}
FORMATS = (
    ("sacd", "SACD", lambda a: a.get("format") == "SACD"),
    ("bluray", "Blu-ray Audio", lambda a: "Blu-ray Audio" in (a.get("tags") or [])),
    ("dvda", "DVD-Audio", lambda a: "DVD-Audio" in (a.get("tags") or [])),
    ("quad", "Quad", lambda a: "Quad" in (a.get("tags") or [])),
    (
        "files",
        "Autres fichiers",
        lambda a: a.get("format") != "SACD" and not SOURCE_TAGS & set(a.get("tags") or []),
    ),
)


def fold(text: str) -> str:
    """Lower case without accents, for sorting and searching ("Déjà" matches "deja")."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def sort_key(name: str) -> str:
    """Sort like the OPPO Music app: articles at the start are ignored ("The Beatles" under B)."""
    return re.sub(r"^(the|les|le|la)\s+", "", fold(name).strip())


def plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def play_request(media_id: str) -> dict | None:
    """Body of POST /api/play for a playable media id, None if it cannot be played."""
    parts = (media_id or "").split(":")
    if len(parts) == 2 and parts[0] == "album" and parts[1]:
        return {"album": parts[1]}
    if len(parts) == 4 and parts[0] == "track" and parts[1]:
        try:
            track = int(parts[3])
            body = {"album": parts[1], "track": track}
            if parts[2] != "f":
                body["disc"] = int(parts[2])
        except ValueError:
            return None
        return body if track > 0 else None
    return None


class Library:
    def __init__(self, data: dict, server: str, img=None):
        self.server = server.rstrip("/")
        self.img = img  # address through the image cache of the integration (None: the server's address)
        self.albums = {a["id"]: a for a in data.get("albums") or [] if a.get("id")}
        artists = [a for a in data.get("artists") or [] if a.get("id") and a.get("albums")]
        self.artists = sorted(artists, key=lambda a: sort_key(a.get("name") or ""))
        self.artist_by_id = {a["id"]: a for a in self.artists}

    # ----------------------------------------------------------------- helpers

    def cover_url(self, album_id: str | None, size: int = 600) -> str | None:
        """Address of a cover on the OPPO Music server (made at this size by the server)."""
        album = self.albums.get(album_id or "")
        if not album or not album.get("cover"):
            return None
        return f"{self.server}/api/cover/{album_id}?s={size}"

    def cover(self, album_id: str | None, size: int = 600) -> str | None:
        url = self.cover_url(album_id, size)
        return self.img(url) if url and self.img else url

    def cover_urls(self) -> list[str]:
        """The covers shown in the lists (albums 600 px, artists 300 px), for the image cache."""
        urls = [self.cover_url(a["id"], 600) for a in self.albums.values()]
        urls += [self.cover_url(a.get("cover"), 300) for a in self.artists]
        return [u for u in urls if u]

    def artist_albums(self, artist: dict) -> list[dict]:
        return [self.albums[i] for i in artist.get("albums") or [] if i in self.albums]

    @staticmethod
    def by_artist(albums) -> list[dict]:
        return sorted(
            albums,
            key=lambda a: (sort_key(a.get("artist") or ""), a.get("year") or 9999, fold(a["title"])),
        )

    # ------------------------------------------------------------------- items

    @staticmethod
    def folder(media_id: str, title: str, subtitle: str | None = None, icon: str | None = None):
        return BrowseMediaItem(
            media_id=media_id,
            title=title,
            subtitle=subtitle,
            media_class=MediaClass.DIRECTORY,
            can_browse=True,
            can_play=False,
            thumbnail=icon,
        )

    def artist_item(self, artist: dict) -> BrowseMediaItem:
        count = len(self.artist_albums(artist))
        return BrowseMediaItem(
            media_id=f"artist:{artist['id']}",
            title=artist.get("name") or "?",
            subtitle=plural(count, "album", "albums"),
            media_class=MediaClass.ARTIST,
            media_type=MediaContentType.ARTIST,
            can_browse=True,
            can_play=False,
            thumbnail=self.cover(artist.get("cover"), 300),
        )

    def album_item(self, album: dict, subtitle: str) -> BrowseMediaItem:
        return BrowseMediaItem(
            media_id=f"album:{album['id']}",
            title=album.get("title") or "?",
            subtitle=subtitle,
            artist=album.get("artist") or None,
            media_class=MediaClass.ALBUM,
            media_type=MediaContentType.ALBUM,
            can_browse=True,
            can_play=True,
            # 600 px: in cover mode the remote shows the current album 448 px wide
            thumbnail=self.cover(album["id"], 600),
        )

    def track_items(self, album: dict, detail: dict) -> list[BrowseMediaItem]:
        items = []
        discs = detail.get("discs") or []
        album_artist = fold(album.get("artist") or "")

        def performer(track):
            name = track.get("performer") or track.get("artist") or ""
            return name if name and fold(name) != album_artist else None

        if discs:
            several = len(discs) > 1
            for index, disc in enumerate(discs):
                for track in disc.get("tracks") or []:
                    n = int(track.get("n") or 0)
                    if n <= 0:
                        continue
                    items.append(
                        BrowseMediaItem(
                            media_id=f"track:{album['id']}:{index}:{n}",
                            title=track.get("title") or f"Piste {n}",
                            subtitle=f"Disque {index + 1}" if several else None,
                            artist=performer(track),
                            media_class=MediaClass.TRACK,
                            media_type=MediaContentType.TRACK,
                            can_play=True,
                            duration=round(track["duration"]) if track.get("duration") else None,
                        )
                    )
        else:
            for track in detail.get("tracks") or []:
                n = int(track.get("n") or 0)
                if n <= 0:
                    continue
                items.append(
                    BrowseMediaItem(
                        media_id=f"track:{album['id']}:f:{n}",
                        title=track.get("title") or f"Piste {n}",
                        artist=performer(track),
                        media_class=MediaClass.TRACK,
                        media_type=MediaContentType.TRACK,
                        can_play=True,
                        duration=round(track["duration"]) if track.get("duration") else None,
                    )
                )
        return items

    # ------------------------------------------------------------------ browse

    def browse(self, media_id: str | None, detail: dict | None = None):
        """(container item, all its child items) for a media id. KeyError if it is unknown."""
        media_id = media_id or ROOT
        if media_id == ROOT:
            items = [
                self.folder(
                    "artists",
                    "Artistes",
                    plural(len(self.artists), "artiste", "artistes"),
                    ICONS["artists"],
                ),
                self.folder("albums", "Albums", plural(len(self.albums), "album", "albums"), ICONS["albums"]),
                self.folder("recent", "Ajouts récents", None, ICONS["recent"]),
                self.folder("formats", "Par format", None, ICONS["formats"]),
            ]
            return self.folder(ROOT, "OPPO Music"), items
        if media_id == "artists":
            return self.folder(media_id, "Artistes"), [self.artist_item(a) for a in self.artists]
        if media_id == "albums":
            albums = sorted(
                self.albums.values(),
                key=lambda a: (sort_key(a.get("title") or ""), sort_key(a.get("artist") or "")),
            )
            return self.folder(media_id, "Albums"), [self.album_item(a, labels.album_line(a)) for a in albums]
        if media_id == "recent":
            albums = sorted(self.albums.values(), key=lambda a: -(a.get("added") or 0))
            return self.folder(media_id, "Ajouts récents"), [
                self.album_item(a, labels.album_line(a)) for a in albums[:RECENT_COUNT]
            ]
        if media_id == "formats":
            items = []
            for key, title, test in FORMATS:
                count = sum(1 for a in self.albums.values() if test(a))
                if count:
                    items.append(
                        self.folder(
                            f"format:{key}",
                            title,
                            plural(count, "album", "albums"),
                            ICONS["format"],
                        )
                    )
            return self.folder(media_id, "Par format"), items
        kind, _, ident = media_id.partition(":")
        if kind == "format":
            found = next((f for f in FORMATS if f[0] == ident), None)
            if found is None:
                raise KeyError(media_id)
            _, title, test = found
            albums = self.by_artist(a for a in self.albums.values() if test(a))
            return self.folder(media_id, title), [self.album_item(a, labels.album_line(a)) for a in albums]
        if kind == "artist":
            artist = self.artist_by_id[ident]
            container = BrowseMediaItem(
                media_id=media_id,
                title=artist.get("name") or "?",
                media_class=MediaClass.ARTIST,
                media_type=MediaContentType.ARTIST,
                can_browse=True,
                can_play=False,
                thumbnail=self.cover(artist.get("cover"), 300),
            )
            return container, [
                self.album_item(a, labels.artist_album_line(a)) for a in self.artist_albums(artist)
            ]
        if kind == "album":
            album = self.albums[ident]
            container = BrowseMediaItem(
                media_id=media_id,
                title=album.get("title") or "?",
                # the album page shows this line under the title
                artist=labels.header_line(album),
                media_class=MediaClass.ALBUM,
                media_type=MediaContentType.ALBUM,
                can_browse=True,
                can_play=True,
                thumbnail=self.cover(album["id"], 600),
            )
            return container, self.track_items(album, detail or {})
        raise KeyError(media_id)

    # ------------------------------------------------------------------- match

    def match_album(self, artist: str | None, title: str | None, kind: str | None = None) -> dict | None:
        """The library album the player reports (artist and disc title), when the server lost track of
        what it started. Among editions with the same title, a SACD when the player reads DSD."""
        wanted_title, wanted_artist = fold(title or "").strip(), fold(artist or "").strip()
        if not wanted_title:
            return None
        found = [
            a
            for a in self.albums.values()
            if fold(a.get("title") or "").strip() == wanted_title
            and (not wanted_artist or fold(a.get("artist") or "").strip() == wanted_artist)
        ]
        if not found:
            return None
        dsd = "DSD" in (kind or "").upper() or "SACD" in (kind or "").upper()
        found.sort(key=lambda a: (a.get("format") == "SACD") != dsd)
        return found[0]

    # ------------------------------------------------------------------ search

    def search(self, query: str, media_classes=None) -> list[BrowseMediaItem]:
        """Artists whose name and albums whose title or artist contain the query."""
        needle = fold(query).strip()
        if not needle:
            return []
        classes = {str(c) for c in media_classes} if media_classes else {"artist", "album"}
        results = []
        if "artist" in classes:
            results += [self.artist_item(a) for a in self.artists if needle in fold(a.get("name"))]
        if "album" in classes:
            albums = self.by_artist(
                a
                for a in self.albums.values()
                if needle in fold(a.get("title")) or needle in fold(a.get("artist"))
            )
            results += [self.album_item(a, labels.album_line(a)) for a in albums]
        return results
