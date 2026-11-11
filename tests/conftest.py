import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "intg-oppo-music"))

SERVER = "http://192.168.2.208:8098"


def album(id_, artist, artist_id, title, year, fmt, layouts, tags=(), channels=None, added=0, cover=True):
    return {
        "id": id_,
        "artist": artist,
        "artistId": artist_id,
        "title": title,
        "year": year,
        "tags": list(tags),
        "format": fmt,
        "channels": channels,
        "layouts": list(layouts),
        "added": added,
        "cover": cover,
        "count": 1,
    }


@pytest.fixture
def library_data():
    albums = [
        album(
            "wywh", "Pink Floyd", "pf", "Wish You Were Here", 1975, "SACD", ["5.1", "2.0"], ["SACD"], added=30
        ),
        album(
            "dsotm",
            "Pink Floyd",
            "pf",
            "The Dark Side Of The Moon",
            1973,
            "FLAC",
            ["4.0"],
            ["Blu-ray Audio", "Quad"],
            channels="4.0",
            added=10,
        ),
        album(
            "abbey",
            "The Beatles",
            "tb",
            "Abbey Road",
            1969,
            "FLAC",
            ["5.1"],
            ["Blu-ray Audio"],
            channels="5.1",
            added=20,
        ),
        album("foxtrot", "Genesis", "ge", "Foxtrot", 1972, "SACD", ["5.1", "2.0"], ["SACD"], added=5),
        album(
            "piaf",
            "Édith Piaf",
            "ep",
            "La Vie en rose",
            None,
            "FLAC",
            ["2.0"],
            channels="2.0",
            added=40,
            cover=False,
        ),
        album(
            "ahm",
            "Pink Floyd",
            "pf",
            "Atom Heart Mother",
            1970,
            "FLAC",
            ["4.0"],
            ["Quad", "Q8"],
            channels="4.0",
            added=1,
        ),
    ]
    artists = [
        {"id": "pf", "name": "Pink Floyd", "cover": "wywh", "albums": ["ahm", "dsotm", "wywh"]},
        {"id": "tb", "name": "The Beatles", "cover": "abbey", "albums": ["abbey"]},
        {"id": "ge", "name": "Genesis", "cover": "foxtrot", "albums": ["foxtrot"]},
        {"id": "ep", "name": "Édith Piaf", "cover": None, "albums": ["piaf"]},
        {"id": "empty", "name": "Nobody", "cover": None, "albums": []},
    ]
    return {"artists": artists, "albums": albums, "audioFiles": True, "version": "0.1.1"}


@pytest.fixture
def library(library_data):
    from library import Library

    return Library(library_data, SERVER + "/")


@pytest.fixture
def wywh_detail():
    return {
        "discs": [
            {
                "name": "Wish You Were Here",
                "file": "wywh.iso",
                "areas": [{"dsd": 64, "channels": "5.1"}, {"dsd": 64, "channels": "2.0"}],
                "tracks": [
                    {
                        "n": 1,
                        "title": "Shine On You Crazy Diamond (Parts I - V)",
                        "duration": 815.67,
                        "performer": "Pink Floyd",
                    },
                    {
                        "n": 2,
                        "title": "Welcome To The Machine",
                        "duration": 446.48,
                        "performer": "Pink Floyd",
                    },
                ],
            }
        ],
        "tracks": [],
    }
