# Changelog

## 0.1.1 — 2026-11-13

Validated on the Remote 3 by the maintainer (test versions 0.1.1-test1 and -test2).

- Covers kept on the Remote: the integration keeps a copy of each album cover and serves it itself
  (port 9310), so the lists open at once instead of downloading the covers again over Wi-Fi. Covers
  are downloaded one after the other in the background and kept as they are (nothing is resized on
  the Remote's small processor).
- Sensor "Signal Oppo": two optional setup settings, font size (1 = 70 %, 2 = 80 %...) and colour
  (#rrggbb or a colour name). Both off by default.

## 0.1.0 — 2026-11-11

First release, validated on the Remote 3 by the maintainer (test versions 0.1.0-test1 to -test7 below).

- Media player "OPPO Music": browse the OPPO Music library (artists, albums A–Z, recent additions,
  formats) with covers and format lines, search, play an album or a track, now playing with
  "artist · format", position, repeat and shuffle.
- Sensor "Signal Oppo": what the player reads ("DSD 5.1", "DSD 2.0", "PCM 24/96 5.1").
- Simple commands PURE_AUDIO_ON (waits for the player to have fully started), PURE_AUDIO_OFF and
  OPPO_OFF (Pure Audio off, then power off, checked and sent again: the player may acknowledge
  "power off" right after a Pure Audio switch and stay on).
- Nothing is asked through the oppo-multiplexer while the player is in standby (port 436 closed, or
  #QPW "OFF"): the player then leaves the transport queries unanswered and each held the multiplexer
  10 s, which made the remote's own Oppo driver fail to power the player on.

## 0.1.0-test7 — 2026-11-11

- **The OPPO stayed on at the end of the music activity** (12:53 and 15:06): its "power off" came
  0.8 s after Pure Audio was switched off; the player answered "OK OFF" and stayed on, so the
  remote's Oppo driver could not tell. New simple command **OPPO_OFF** for the stop sequence:
  Pure Audio off, then #POF, checked with #QPW and sent again every 2 s while the player says it is
  on; answered within 9 s and never goes on after that (another activity may be starting the
  player).

## 0.1.0-test6 — 2026-11-11

- For a few seconds after "power off" the player's HTTP port is still open while it already ignores
  the transport queries: a status poll then held the multiplexer 10 s, and the next activity's
  power-on got through with 0.6 s to spare. With port 436 open, the driver now asks #QPW first
  (answered at once, "OK OFF" in that window) and only asks the server when the player is on.

## 0.1.0-test5 — 2026-11-11

- The standby check of test4 used #QPW through the oppo-multiplexer, but it is not certain the
  player answers #QPW after a long standby (an unanswered query holds the multiplexer 10 s). The
  driver now checks the player's HTTP port (436) directly: closed in standby, open once its main
  software runs. `GET /api/status` is only asked when it is open. When the server reports the
  player unreachable although the port is open (its IP control does not answer), the driver polls
  every 60 s instead of piling up queries. The player shows on as soon as PURE_AUDIO_ON has seen it
  start.

## 0.1.0-test4 — 2026-11-11 (replaced by test5 the same day)

- **The Oppo did not power on at the start of the music activity** (step 2, the remote's Oppo
  driver answered an error after 6 s and the OPPO only started afterwards). Cause: while the OPPO
  is in standby it answers #QPW but none of the transport queries the OPPO Music server sends for
  `GET /api/status` (#QPL, #QTK, #QCE, #QCR, #QRP); the oppo-multiplexer waits 10 s for each, so
  every status poll of this driver held it for 50 s, and the Oppo driver's power-on waited behind.
  The driver asked #QPW first and only asked the server once the player was on (15 s while off).
  After PURE_AUDIO_ON the state is read at once.

## 0.1.0-test3 — 2026-11-11

- **Pure Audio at the start of an activity**: right after "power on" the OPPO confirms commands, then
  resets Pure Audio when its main software starts (seen on the remote: set in 0.15 s, lost). The
  driver now waits until the player has fully started (its HTTP interface, port 436, answers after the
  control-app notice) plus 5 s. New optional setting "OPPO address" (192.168.2.195).
- New sensor **Signal Oppo**: what the player reads, as its front display shows it: "DSD 5.1" /
  "DSD 2.0" for the SACD area played, "PCM 24/96 5.1" for FLAC, "DSD" when started elsewhere.
- When the OPPO Music server loses track of what it started (its 40 s rule while a disc image loads),
  the driver finds the album from what the player reports, so the title, cover and format stay right.

## 0.1.0-test2 — 2026-11-11

- Simple commands **PURE_AUDIO_ON** and **PURE_AUDIO_OFF** for activity sequences and buttons. The
  OPPO only has a Pure Audio toggle (#PUR, answered "OK ON" / "OK OFF"): the driver toggles, reads the
  answer and toggles again when needed, through the oppo-multiplexer (new optional setting "OPPO IP
  control", by default the OPPO Music server's host, port 23). PURE_AUDIO_ON is answered at once and
  waits up to 2 min in the background for the player to start up; PURE_AUDIO_OFF is waited for (12 s
  at most), so that a following power-off step comes after it.

## 0.1.0-test1 — 2026-11-11

First test version.

- Media player entity "OPPO Music" with browsing, search and playback through an OPPO Music server.
- Library: Artistes, Albums (A–Z), Ajouts récents, Par format (SACD, Blu-ray Audio, DVD-Audio,
  Quad, other files); artist → albums by year → album page with its tracks (disc images and audio
  files, several discs).
- Info lines sized for the remote ("1975 · SACD 5.1/2.0", "Pink Floyd · 1975 · SACD 5.1/2.0").
- Now playing: cover, track, "artist · format" (SACD area from the player's SACD priority),
  position, repeat, shuffle; play/pause, stop, previous/next, seek, repeat, shuffle.
- Status polled every 3 s while playing, 10 s when idle, 30 s while the player is off (the server
  then takes about 15 s to give up on it); polling stops while the remote sleeps.
- A play command is answered within 8 s; starting a disc image can take longer and goes on in the
  background.
