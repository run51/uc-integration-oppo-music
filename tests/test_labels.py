import labels


def by_id(data, id_):
    return next(a for a in data["albums"] if a["id"] == id_)


def test_format_labels(library_data):
    assert labels.format_label(by_id(library_data, "wywh")) == "SACD 5.1/2.0"
    assert labels.format_label(by_id(library_data, "abbey")) == "Blu-ray 5.1"
    assert labels.format_label(by_id(library_data, "abbey"), long=True) == "Blu-ray Audio 5.1"
    assert labels.format_label(by_id(library_data, "dsotm")) == "Blu-ray 4.0"
    assert labels.format_label(by_id(library_data, "ahm")) == "Quad 4.0"
    assert labels.format_label(by_id(library_data, "piaf")) == "FLAC 2.0"
    dvd = {"format": "FLAC", "tags": ["DVD-Audio"], "channels": "5.1", "layouts": ["5.1"]}
    assert labels.format_label(dvd) == "DVD-Audio 5.1"
    assert labels.format_label({"format": "DSD", "tags": [], "channels": None, "layouts": []}) == "DSD"


def test_lines_fit_the_remote(library_data):
    assert labels.artist_album_line(by_id(library_data, "wywh")) == "1975 · SACD 5.1/2.0"
    # "1973 · Blu-ray Audio 4.0" is 24 characters: the short medium name is used
    assert labels.artist_album_line(by_id(library_data, "dsotm")) == "1973 · Blu-ray 4.0"
    assert labels.artist_album_line(by_id(library_data, "piaf")) == "FLAC 2.0"
    assert labels.album_line(by_id(library_data, "foxtrot")) == "Genesis · SACD 5.1/2.0"
    assert labels.album_line(by_id(library_data, "wywh")) == "Pink Floyd · SACD"
    assert labels.header_line(by_id(library_data, "wywh")) == "Pink Floyd · 1975 · SACD 5.1/2.0"


def test_header_keeps_the_format_visible():
    bowie = {
        "artist": "David Bowie",
        "year": 1972,
        "format": "FLAC",
        "channels": "5.1",
        "layouts": ["5.1"],
        "tags": ["Blu-ray Audio", "2003 remix"],
    }
    assert labels.header_line(bowie) == "David Bowie · 1972 · Blu-ray 5.1"
    long_name = {
        "artist": "The Alan Parsons Project Orchestra",
        "year": 1976,
        "format": "SACD",
        "layouts": ["5.1", "2.0"],
        "tags": [],
    }
    assert labels.header_line(long_name) == "1976 · SACD 5.1/2.0"


def test_player_line_follows_the_sacd_area(library_data):
    wywh = by_id(library_data, "wywh")
    assert labels.player_line(wywh, "mch") == "Pink Floyd · SACD 5.1"
    assert labels.player_line(wywh, None) == "Pink Floyd · SACD 5.1"
    assert labels.player_line(wywh, "stereo") == "Pink Floyd · SACD 2.0"
    assert labels.player_line(wywh, "cd") == "Pink Floyd · SACD, couche CD"
    assert labels.player_line(by_id(library_data, "abbey")) == "The Beatles · Blu-ray Audio 5.1"
    stereo_only = {"artist": "Miles Davis", "format": "SACD", "layouts": ["2.0"], "tags": []}
    assert labels.player_line(stereo_only, "mch") == "Miles Davis · SACD 2.0"


def test_first_fit_falls_back_to_the_last_candidate():
    assert labels.first_fit(["abcdef", "abc"], 4) == "abc"
    assert labels.first_fit(["abcdef", "abcde"], 4) == "abcde"
    assert labels.first_fit(["", None], 4) == ""
