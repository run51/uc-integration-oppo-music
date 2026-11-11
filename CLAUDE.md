# Project context — OPPO Music integration for Unfolded Circle

Read this file at the start of a session. It holds the context and decisions that cannot be derived
from the code. **Talk to the maintainer in French** (code, comments and repository documentation stay
in English).

## Goal

From the Remote 3 activity "Ecouter musique lecteur BluRay", browse the maintainer's OPPO Music
library like Emby for films: the player widget doubles as the library (long press on the cover or
its library icon), artists → albums → tracks, cover mode, and the album type ("SACD 5.1/2.0",
"Blu-ray Audio 5.1") under covers and titles, as in the OPPO Music Android app.

Chain: `Remote 3 → this driver (WebSocket Integration-API) → OPPO Music server (HTTP 8098) → OPPO`

The OPPO Music server lives in `~/projets/emby-oppo-remote/music/server.py` (container `oppo-music`
on Unraid 192.168.2.208, image python:3.13-alpine, app mounted from `/mnt/user/appdata/oppo-music`).
That folder is deliberately not committed in the emby-oppo-remote repository.

## Current state (2026-11-11)

- **0.1.0** released 2026-11-11 (maintainer: "passe le pilote OPPO Music en 0.1.0" after "tout marche"):
  same code as 0.1.0-test7. The Unraid container still runs the image tagged `oppo-music-uc:0.1.0-test1`
  (runtime only, the app is mounted from appdata), so no rebuild was needed. Not a git repository yet.
- 2026-11-11 17:46: the maintainer reports "tout marche" (films, music activity start with Pure Audio, OPPO off
  at the stop, Roon page). Logs since 17:35: no multiplexer timeout at all. Next: version 0.1.0 when the
  maintainer agrees (not during a listening session: the container restart blinks the widget), then packaging
  on the remote (GitHub repository to be created by the maintainer).
- **0.1.0-test7** (deployed 2026-11-11 15:19): simple command **OPPO_OFF** (Pure Audio off, then #POF
  checked with #QPW and sent again every 2 s, answered within 9 s, never continues after). The music
  activity's stop sequence is now OPPO_OFF, Oppo driver off (fallback), Denon off (backup in the remote
  session scratchpad: backup-musique-avant-oppo-off.json). Reason: at 12:53 and 15:06 the OPPO stayed on —
  its #POF came 0.8 s after the Pure Audio switch, it answered "OK OFF" (the Oppo driver checks the
  reply's command code, so this was the player's own answer) and did not power off; its video output only
  came back ~9 s after the switch. Seen working at 17:18 ("OPPO off after 7.5 s", the player ignored the first #POF).
- **0.1.0-test6** (deployed 15:11): #QPW before `GET /api/status` when port 436 is open.
- **0.1.0-test5** (deployed 2026-11-11 14:06): the standby check is the player's HTTP port 436 (direct, not
  through the multiplexer) instead of #QPW; 60 s polls when the server says unreachable while 436 is
  open. 45 tests.
- **0.1.0-test4** (deployed 2026-11-11 13:58): #QPW before `GET /api/status` (see the multiplexer fact below);
  fixes the music activity failing at step 2 (Oppo power-on) — seen at 13:43, the maintainer had to
  start the activity again. Pure Audio at start then worked ("Pure Audio on" 5 s after the command)
  and a SACD looked right to the maintainer ("ça a l'air d'aller"). 44 tests.
- **0.1.0-test3** (deployed 12:15): Pure Audio waits for the player's main software (HTTP 436) + 5 s;
  sensor `oppo_music.main.oppo_signal` ("Signal Oppo") left of "Son ampli" (both 2×3, player back to 4×8);
  album matched from the player's info when the server lost `now`. config.json has `oppo_host`. 42 tests.
  The maintainer confirmed the Signal Oppo tile on FLAC (two albums started outside the remote: server log
  `initAndPlay`, no driver command, so the driver follows plays it did not start); PURE_AUDIO_OFF at the
  activity stop answered "Pure Audio off" in 0.6 s. Not seen yet: PURE_AUDIO_ON with the new wait (the
  activity was not restarted since the deploy) and a SACD (expected "DSD 5.1").
- **0.1.0-test2** (deployed 11:47): Pure Audio simple commands (PURE_AUDIO_ON in the music activity's start
  sequence, PURE_AUDIO_OFF first in its stop sequence, at the maintainer's request; the "Pure Audio Oppo"
  button was removed from the page and the player enlarged to 4×9). After the driver restart the remote
  only showed the new `simple_commands` after `GET /api/intg/instances/oppo_music.main/entities?filter=ALL`.
  37 tests green.
- **0.1.0-test1**: 29 tests green, checked against the real server with `tools/ws_check.py`
  (setup, 110 artists / 263 albums, artist and album pages, search, formats, 404).
- Deployed for testing on Unraid: image `oppo-music-uc:0.1.0-test1` built locally from
  `/mnt/user/appdata/oppo-music-uc/app`, container `oppo-music-uc` (host network, port 9095,
  `UC_INTEGRATION_INTERFACE=192.168.2.208`, config in `appdata/oppo-music-uc/config`, template
  `my-oppo-music-uc.xml`, listed in `/var/lib/docker/unraid-autostart`).
  **Update = copy the files into `appdata/oppo-music-uc/app` and `docker restart oppo-music-uc`.**
- The remote's discovery did not list the driver although its mDNS announcement is visible on the
  LAN (same kind of mDNS trouble as Dock 1), so it was registered by address:
  `POST /api/intg/drivers` with driver.json + `driver_url: ws://192.168.2.208:9095`.
  Integration `oppo_music.main`, entity `oppo_music.main.oppo_music`.
- Activity "Ecouter musique lecteur BluRay" page `main` (since 2026-11-11 16:01, maintainer's wish: below each
  player only the OPPO signal and the Denon signal, like the Lecture BluRay "Emby" page): grid 4×12, OPPO Music
  player 4×8, "Signal Oppo" band 4×2 (row 8), Denon "Son ampli" band 4×2 (row 10); page 2 "Roon" the same with
  the Roon zone OPPO and the Oppo driver's AudioType sensor labelled "Signal Oppo" (backup
  backup-musique-avant-pages-signaux.json). Before: (the Oppo player widget, its DiscType / AudioType
  tiles and the "Pure Audio Oppo" button were removed; backups in the remote session scratchpad:
  backup-page-musique-avant-oppo-music.json, backup-page-musique-avant-sans-pure-audio.json,
  backup-musique-avant-sequences-pure-audio.json, backup-page-musique-avant-signal.json).
- Waiting for the maintainer's test of Pure Audio at activity start and of a SACD.

## Decisions and facts

- Test versions are `X.Y.Z-testN`; a release only after the maintainer validated it on the remote.
- Never start playback on the OPPO, or turn it on, without the maintainer present: `tools/ws_check.py`
  sends no play command on purpose.
- Right after #PON the OPPO answers IP control at once (QPW "OK ON", #PUR "OK ON") but its main
  software starts later and resets Pure Audio: wait for HTTP 436 (after the UDP notice) before #PUR.
- The OPPO Music server forgets `now` (its 40 s idle rule) when a disc image is slow to load; status then
  carries `info` (title = disc title, artist, kind "SACD DSD") from the player's HTTP interface.
- 2026-11-11 13:53: the remote's Oppo driver (custom build 0.0.34-hdr1, see
  `~/projets/remote/oppo-driver/`) sent #QHS every ~10 s while a SACD image played from NFS (its
  "file playback" rule: No Disc + playing + duration > 300 s). The OPPO does not answer #QHS for
  audio; each one held the multiplexer 10 s, and after ~2 min the OPPO stopped answering any IP
  control query (even #QPW) while its HTTP port still worked: the upstream code warns that QHS can
  lock up the player. Fixed in the Oppo driver 0.0.34-hdr2 (installed 2026-11-11 14:25): #QHS for a
  "No Disc" playback only once HTTP getglobalinfo says it is not music.
- The OPPO front display shows what it reads (DSD / DSD MULTICH). The Denon reported "MULTI CH IN"
  (labelled "Multi-ch PCM" by the Denon driver) while a SACD played: that label does not prove a PCM
  conversion, do not tell the maintainer the OPPO converts DSD without checking its settings.
- In standby the OPPO does not answer the transport queries (#QPL, #QTK...) but answers `#QPW` at once
  ("QPW OK OFF": right after power-off, and still 5 min later). Port 436 is NOT a standby sign: it stayed
  open in standby once a control app had announced itself (15:07–15:12), and it stays closed after a
  power cut until that notice, even when the player is on. So: 436 closed → do not ask anything;
  436 open → #QPW first, the transport queries only when it says ON (driver test6, server 0.1.3).
  The server's `GET /api/status` sends 5 of them (#QPL #QTK #QCE #QCR #QRP, 3 s each on its side,
  ~15 s, `reachable: false`), and the oppo-multiplexer (args `1024 192.168.2.195:23 10 5`) waits 10 s
  for each and serializes everything: 50 s blocked per status. The remote's Oppo driver gives up a
  power-on after 2 × 3 s (#PON then expects "@OK ON", error 400 "Unknown command"), so the music
  activity failed at step 2. Since test5 the driver checks port 436 first (`read_status`) and never
  calls `/api/status` while the player is off. Any other client polling `/api/status` while the OPPO is off
  (the OPPO Music app or web page) can still block the multiplexer: the server should check port 436
  before its IP control queries: OPPO Music server 0.1.2 (14:18): no IP control while 436 is closed,
  stops at the first unanswered query; 0.1.3 (15:19, backups `server.py.bak-0.1.1` / `-0.1.2`): #QPW
  first, standby still reported `reachable: false` (with `state: "OFF"` the web page would show the
  last album as playing, since `now` is kept). Its web app polls `/api/status` every 2 s / 6 s.
- `POST /api/play` wakes the OPPO (UDP login notice + #PON), mounts NFS and starts the disc image:
  10–60 s. The driver answers the remote after 8 s and lets it finish in the background.
- The remote shows only title + artist in its player widget (never media_album): second line =
  "artist · format". Browser rows and the cover-mode subtitle show one Space Mono 22 px line
  (≈22 characters); the album page header line ≈34 characters.
- Later (maintainer's wish): once validated, package it to run on the remote itself like the Denon
  driver (`~/projets/denon-rs-232`: GitHub repo + aarch64 build workflow). Needs a GitHub repository,
  which the maintainer creates.

## Layout

- `driver.json` — metadata and setup schema (server address).
- `intg-oppo-music/driver.py` — Integration API glue: setup, entity, browse/search, commands, polling.
- `intg-oppo-music/library.py` — browse tree and search (pure).
- `intg-oppo-music/labels.py` — format labels and info lines (pure).
- `intg-oppo-music/status.py` — server status → media player attributes (pure).
- `intg-oppo-music/client.py` — HTTP client (standard library, run in a thread).
- `tests/` — pytest; `tools/ws_check.py` — talk to a running driver like the remote does.
- Run the tests with the Denon project's virtualenv if needed:
  `~/projets/denon-rs-232/.venv/bin/python -m pytest` (python3-venv is not installed here).
