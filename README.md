# OPPO Music for the Unfolded Circle Remote

An integration for the Unfolded Circle Remote Two / Remote 3 that exposes one media player,
**OPPO Music**, backed by an [OPPO Music](../emby-oppo-remote/music) server:

- **Browse** the library from the remote: artists → albums (by year) → tracks, all albums A–Z,
  recently added albums, albums by medium (SACD, Blu-ray Audio, DVD-Audio, Quad, other files).
  Covers come from the server; the remote shows them in lists or in its cover mode.
- **Search** artists and albums by name (accents and case ignored).
- **Play** an album or a track: the server wakes the OPPO, mounts the music share and starts it.
- **Now playing**: cover, track title, then "artist · format" ("Pink Floyd · SACD 5.1": for a SACD,
  the area the player's SACD priority setting selects), position, repeat and shuffle.

The remote never shows the album name in its player widget, hence the format on the second line.
Info lines are sized for the remote's Space Mono 22 px text: 22 characters in a list row or under a
cover, 34 under an album title; longer candidates fall back to shorter ones (see `labels.py`).

## Requirements

- An OPPO Music server (0.1.1 or later) reachable from the remote, e.g. `http://192.168.2.208:8098`.
  The remote loads the covers from that address directly.
- An OPPO UDP-203 / UDP-205 driven by that server.

## Run

Docker, with host networking so the remote can discover the driver (mDNS) and reach its port:

```sh
docker build -t oppo-music-uc:0.1.0 .
docker run -d --name oppo-music-uc --net host \
  -e UC_INTEGRATION_INTERFACE=192.168.2.208 -e UC_INTEGRATION_HTTP_PORT=9095 \
  -v /mnt/user/appdata/oppo-music-uc/config:/config oppo-music-uc:0.1.0
```

`unraid/oppo-music-uc.xml` is the matching Unraid template (it mounts the driver files from
`appdata/oppo-music-uc/app`, so an update is: copy the files, restart the container).

Without Docker: `UC_CONFIG_HOME=./config python intg-oppo-music/driver.py` from this folder
(`driver.json` is read from the working directory).

## Add it to the remote

1. Integrations → add → OPPO Music, if discovery lists it. Otherwise register it by address with the
   remote's REST API: `POST /api/intg/drivers` with the content of `driver.json` (without `port`)
   plus `"driver_url": "ws://<host>:9095"`.
2. Setup asks for the OPPO Music server address.
3. Add the **OPPO Music** media player entity, then put it on an activity page. Long press on its
   cover, or its library icon, opens the library.

## Development

```sh
pip install -r requirements-dev.txt
pytest
ruff check .
python tools/ws_check.py ws://127.0.0.1:9095 http://192.168.2.208:8098   # talk to a running driver
```

`tools/ws_check.py` behaves like the remote (setup, entities, browsing, search) and never sends a
play command.
