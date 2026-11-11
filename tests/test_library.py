import pytest
from conftest import SERVER
from library import play_request


def ids(items):
    return [i.media_id for i in items]


def test_root(library):
    container, items = library.browse(None)
    assert container.media_id == "root"
    assert ids(items) == ["artists", "albums", "recent", "formats"]
    assert items[0].subtitle == "4 artistes"  # the artist without albums is left out
    assert items[1].subtitle == "6 albums"
    assert all(i.can_browse and not i.can_play for i in items)
    assert items[0].thumbnail == "icon://uc:users"


def test_artists_sorted_without_articles_and_accents(library):
    _, items = library.browse("artists")
    assert [i.title for i in items] == ["The Beatles", "Édith Piaf", "Genesis", "Pink Floyd"]
    beatles = items[0]
    assert beatles.media_id == "artist:tb"
    assert beatles.subtitle == "1 album"
    assert beatles.thumbnail == f"{SERVER}/api/cover/abbey?s=300"
    assert items[1].thumbnail is None  # no cover
    assert beatles.can_browse and not beatles.can_play


def test_artist_page_lists_albums_by_year(library):
    container, items = library.browse("artist:pf")
    assert container.title == "Pink Floyd"
    assert container.media_class == "artist"
    assert ids(items) == ["album:ahm", "album:dsotm", "album:wywh"]
    wywh = items[2]
    assert wywh.subtitle == "1975 · SACD 5.1/2.0"
    assert wywh.thumbnail == f"{SERVER}/api/cover/wywh?s=600"
    assert wywh.can_browse and wywh.can_play
    assert wywh.media_class == "album"


def test_album_page(library, wywh_detail):
    container, items = library.browse("album:wywh", wywh_detail)
    assert container.media_class == "album"  # the remote shows it as an album page
    assert container.title == "Wish You Were Here"
    assert container.artist == "Pink Floyd · 1975 · SACD 5.1/2.0"
    assert container.can_play
    assert ids(items) == ["track:wywh:0:1", "track:wywh:0:2"]
    assert items[0].duration == 816
    assert items[0].subtitle is None and items[0].artist is None  # same artist: nothing repeated
    assert all(i.can_play and not i.can_browse for i in items)


def test_album_with_several_discs_and_audio_files(library):
    detail = {
        "discs": [
            {"tracks": [{"n": 1, "title": "A"}]},
            {"tracks": [{"n": 1, "title": "B", "performer": "Guest"}]},
        ],
        "tracks": [],
    }
    _, items = library.browse("album:wywh", detail)
    assert ids(items) == ["track:wywh:0:1", "track:wywh:1:1"]
    assert [i.subtitle for i in items] == ["Disque 1", "Disque 2"]
    assert items[1].artist == "Guest"
    files = {"discs": [], "tracks": [{"n": 1, "title": "Come Together", "duration": 259.9}]}
    _, items = library.browse("album:abbey", files)
    assert ids(items) == ["track:abbey:f:1"]
    assert items[0].duration == 260


def test_lists_of_albums(library):
    _, albums = library.browse("albums")
    assert [i.title for i in albums] == [
        "Abbey Road",
        "Atom Heart Mother",
        "The Dark Side Of The Moon",
        "Foxtrot",
        "La Vie en rose",
        "Wish You Were Here",
    ]
    assert albums[0].subtitle == "The Beatles · Blu-ray"  # 25 characters with " 5.1": too long
    _, recent = library.browse("recent")
    assert ids(recent)[:3] == ["album:piaf", "album:wywh", "album:abbey"]


def test_formats(library):
    _, folders = library.browse("formats")
    assert [(f.title, f.subtitle) for f in folders] == [
        ("SACD", "2 albums"),
        ("Blu-ray Audio", "2 albums"),
        ("Quad", "2 albums"),
        ("Autres fichiers", "1 album"),
    ]
    _, sacd = library.browse("format:sacd")
    assert ids(sacd) == ["album:foxtrot", "album:wywh"]  # by artist, then year


def test_unknown_ids(library):
    for media_id in ("artist:nope", "album:nope", "format:nope", "weird"):
        with pytest.raises(KeyError):
            library.browse(media_id)


def test_search(library):
    assert ids(library.search("piaf")) == ["artist:ep", "album:piaf"]
    assert ids(library.search("EDITH")) == ["artist:ep", "album:piaf"]  # accents and case ignored
    assert ids(library.search("floyd", ["album"])) == ["album:ahm", "album:dsotm", "album:wywh"]
    assert ids(library.search("moon")) == ["album:dsotm"]
    assert library.search("  ") == []


def test_play_request():
    assert play_request("album:wywh") == {"album": "wywh"}
    assert play_request("track:wywh:0:3") == {"album": "wywh", "disc": 0, "track": 3}
    assert play_request("track:abbey:f:2") == {"album": "abbey", "track": 2}
    for bad in ("artist:pf", "track:wywh:x:1", "track:wywh:0:0", "album:", "", None):
        assert play_request(bad) is None


def test_match_album(library, library_data):
    assert library.match_album("Pink Floyd", "wish you were here")["id"] == "wywh"
    assert library.match_album("EDITH PIAF", "La Vie en Rose")["id"] == "piaf"
    assert library.match_album("Pink Floyd", "Unknown") is None
    assert library.match_album(None, "") is None
    # two editions: the SACD when the player reads DSD, else the other one
    library.albums["dsotm-sacd"] = dict(
        library.albums["dsotm"], id="dsotm-sacd", format="SACD", layouts=["5.1", "2.0"], tags=["SACD"]
    )
    assert library.match_album("Pink Floyd", "The Dark Side Of The Moon", "SACD DSD")["id"] == "dsotm-sacd"
    assert library.match_album("Pink Floyd", "The Dark Side Of The Moon", None)["id"] == "dsotm"
