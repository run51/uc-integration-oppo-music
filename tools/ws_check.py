#!/usr/bin/env python3
"""Talk to a running driver the way the remote does (Integration API over WebSocket) and print what it
answers: setup, entities, browsing and search. It never sends a play command.

Usage: python tools/ws_check.py ws://127.0.0.1:9095 [http://oppo-music-server:8098]
"""

import asyncio
import json
import sys

import websockets

ENTITY = "oppo_music"


class Remote:
    def __init__(self, ws):
        self.ws = ws
        self.next_id = 1

    async def request(self, msg, data=None, show_events=True):
        req_id = self.next_id
        self.next_id += 1
        payload = {"kind": "req", "id": req_id, "msg": msg}
        if data is not None:
            payload["msg_data"] = data
        await self.ws.send(json.dumps(payload))
        while True:
            reply = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=30))
            if reply.get("kind") == "resp" and reply.get("req_id") == req_id:
                return reply
            if show_events:
                print("   event:", json.dumps(reply, ensure_ascii=False)[:300])

    async def events(self, seconds):
        try:
            while True:
                reply = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=seconds))
                print("   event:", json.dumps(reply, ensure_ascii=False)[:400])
        except TimeoutError:
            pass


def show_browse(title, reply):
    data = reply.get("msg_data") or {}
    media = data.get("media") or {}
    print(f"== {title}: code {reply.get('code')}, {data.get('pagination')}")
    print(
        f"   [{media.get('media_class')}] {media.get('title')!r} artist={media.get('artist')!r}"
        f" thumb={media.get('thumbnail')}"
    )
    for item in media.get("items") or []:
        print(
            f"   - {item['media_id']:28} {item['title'][:34]!r:38} {str(item.get('subtitle'))!r:28}"
            f" play={item.get('can_play')} browse={item.get('can_browse')} dur={item.get('duration')}"
        )
    return media


async def main(url, server):
    async with websockets.connect(url) as ws:
        remote = Remote(ws)
        await remote.events(1)
        print("version:", (await remote.request("get_driver_version")).get("msg_data"))
        if server:
            reply = await remote.request(
                "setup_driver", {"reconfigure": False, "setup_data": {"server": server}}
            )
            print("setup:", reply.get("code"))
            await remote.events(3)
        entities = (await remote.request("get_available_entities")).get("msg_data") or {}
        for e in entities.get("available_entities") or []:
            print(
                "entity:",
                e.get("entity_id"),
                e.get("entity_type"),
                e.get("device_class"),
                sorted(e.get("features") or []),
            )
        print("subscribe:", (await remote.request("subscribe_events", {"entity_ids": [ENTITY]})).get("code"))
        root = show_browse(
            "root",
            await remote.request("browse_media", {"entity_id": ENTITY, "paging": {"page": 1, "limit": 10}}),
        )
        assert [i["media_id"] for i in root["items"]][:2] == ["artists", "albums"]
        artists = show_browse(
            "artists p1",
            await remote.request(
                "browse_media",
                {"entity_id": ENTITY, "media_id": "artists", "paging": {"page": 1, "limit": 5}},
            ),
        )
        show_browse(
            "artists p2",
            await remote.request(
                "browse_media",
                {"entity_id": ENTITY, "media_id": "artists", "paging": {"page": 2, "limit": 3}},
            ),
        )
        found = await remote.request(
            "search_media", {"entity_id": ENTITY, "query": "floyd", "paging": {"page": 1, "limit": 6}}
        )
        data = found.get("msg_data") or {}
        print(f"== search 'floyd': code {found.get('code')}, {data.get('pagination')}")
        for item in data.get("media") or []:
            print(f"   - {item['media_id']:28} {item['title'][:34]!r:38} {item.get('subtitle')!r}")
        artist_id = next(
            (i["media_id"] for i in data.get("media") or [] if i["media_id"].startswith("artist:")),
            artists["items"][0]["media_id"],
        )
        albums = show_browse(
            artist_id,
            await remote.request(
                "browse_media",
                {"entity_id": ENTITY, "media_id": artist_id, "paging": {"page": 1, "limit": 20}},
            ),
        )
        album_id = albums["items"][0]["media_id"]
        sacd = next((i["media_id"] for i in albums["items"] if "SACD" in (i.get("subtitle") or "")), album_id)
        show_browse(
            sacd,
            await remote.request(
                "browse_media", {"entity_id": ENTITY, "media_id": sacd, "paging": {"page": 1, "limit": 50}}
            ),
        )
        show_browse(
            "formats",
            await remote.request(
                "browse_media",
                {"entity_id": ENTITY, "media_id": "formats", "paging": {"page": 1, "limit": 10}},
            ),
        )
        missing = await remote.request("browse_media", {"entity_id": ENTITY, "media_id": "album:nope"})
        print("unknown album:", missing.get("code"))
        states = (await remote.request("get_entity_states")).get("msg_data")
        print("states:", json.dumps(states, ensure_ascii=False)[:600])
        await remote.events(4)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
