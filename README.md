# AMPTemplates-Riftbreaker — The Riftbreaker dedicated server for AMP

**AMP Generic Module** template for the official **The Riftbreaker – Dedicated Server**
(EXOR Studios, free Steam tool, app `4114030`), on **Linux under Wine**, for co-op games of up to
4 players: Open Campaign, Story Campaign or Survival.
Written for TeamKit, a free French game host, on 10 Oct 2026.

> Résumé en français à la fin du fichier.

- CubeCoders ships no Riftbreaker template. A community one exists,
  [Skywardhigh/Riftbreaker-AMPTemplate](https://github.com/Skywardhigh/Riftbreaker-AMPTemplate), for
  **AMP on Windows only** (`Meta.OS=Windows`). This one runs on Linux AMP hosts, in a container.
- Community Docker image used as a reference: [j3n5-group/riftbreaker-docker](https://gitlab.com/j3n5-group/riftbreaker-docker) (GitLab).

## What the server is

| | |
|---|---|
| Steam app | `4114030` *The Riftbreaker - Dedicated Server* (type Tool, `freetodownload`), parent app `780310` |
| Download | SteamCMD, **anonymous** login — EXOR: "you do not even need a Steam account" |
| Platforms | **Windows only**: one depot (`4114031`, 631 MB) + Steamworks redistributables; launch entry `DedicatedServer.bat` → `bin\DedicatedServer.exe` |
| Players | **The game is paid**: every player needs The Riftbreaker on Steam, **same build as the server** (EXOR: "the server app version and the main game MUST MATCH") |
| Linux | not supported by EXOR ("It is highly likely that the dedicated server app will run under Linux, however, we have not tested that") |

## How it runs on Linux

- Image **`cubecoders/ampbase:wine-stable`** (Debian 13, Wine 11.0), container **required**, as
  CubeCoders does for its 51 Windows-only servers (Windrose, StarRupture, Empyrion, Foundry…).
  `ampbase:debian` has no Wine.
- **No Xvfb, no winetricks**: tested, the server starts with Wine's built-in VC++ runtime and no
  display (`unset DISPLAY`). The community image installs `vcrun2022` and `d3dcompiler_47`; neither
  is needed (`d3dcompiler_47.dll` ships in `bin/`).
- Launch line from EXOR's guide: `DedicatedServer.exe cli=1 config=teamkit.cfg`, run from `bin/`,
  the `.cfg` file in the install root. Like `DedicatedServer.bat`, no Steam variable is passed.

### Direct IP only (no Steam server browser)

The config key `disable_steam` chooses the network layer. Tested on 10 Oct 2026:

| `disable_steam` | Result under Wine (anonymous install) |
|---|---|
| `"1"` | **works**: `[NetServerGNS] running as: ip:[::]:6321`, ready in 6–16 s |
| `"0"` (Steam relay, server browser) | **hangs** right after engine start (7 log lines, then nothing for 2 min), with or without `SteamAppId=780310` and `steam_appid.txt`, with or without Xvfb |

So the template forces `disable_steam "1"` and `server_broadcast_enabled "0"`. The server is listed
nowhere; players connect by IP (see *How players join*). The Skywardhigh template reports the same
choice on Windows ("`disable_steam=1` (LAN / direct-IP) — the stable, tested mode").

### One fixed port: 6321/UDP

Only **UDP 6321** is opened (seen with `ss`; no TCP socket). The port **cannot be changed**: no
config variable exists for it (the binary only has `+ip:%s:6321`), and a client told to connect to
`127.0.0.1:6321` fails while `127.0.0.1` works. Consequences: **one Riftbreaker instance per IP
address**, and the AMP port must stay 6321 (the start script refuses any other, with a message).

## Files

| File | Role |
|---|---|
| `riftbreaker.kvp`, `riftbreaker*.json`, `manifest.json` | the AMP template |
| `scripts/AMP_reglages.txt` | settings model, rendered by AMP to `4114030/reglages-amp.txt` (`ConfigType: template`) |
| `scripts/lancer-riftbreaker.sh` | start script (below) |
| `verifier.py` | pre-push checks, must print `Tout est bon.` |

Both `scripts/` files are downloaded from this repository (raw.githubusercontent.com, branch
`main`) at each Update, so **the repository must be public**.

Instance layout: `riftbreaker/4114030/` = server (SteamCMD), `riftbreaker/.wine/` = Wine prefix
(1.4 GB, created once), `riftbreaker/donnees/` = saves, profile and log, `riftbreaker/perso.cfg` =
extra config lines (created once, never overwritten).

## Update stages

1. **SteamCMD** app `4114030`, `ForceDownloadPlatform: Windows`, anonymous (667 MB on disk).
2. **FetchURL** `AMP_reglages.txt` and `lancer-riftbreaker.sh` into the instance root.
3. **`lancer-riftbreaker.sh preparer`**: creates the Wine prefix if missing (`wineboot --init`,
   Mono/Gecko disabled, 11 s), links the game's `Documents/The Riftbreaker` folder to `donnees/`,
   prints the Wine version and the Steam build id.

The prefix is never deleted (unlike CubeCoders' Wine templates, which `rm -rf` it at each Update):
saves live in `donnees/`, outside the prefix, but there is no reason to rebuild 1.4 GB each time.

## How the server is started

AMP runs `/bin/bash lancer-riftbreaker.sh <port>`. The script:

1. checks the port (6321), the game, Wine and the prefix;
2. reads `4114030/reglages-amp.txt` (one `key=value` per line) and validates every value;
3. picks the game to run (see *Saves and resume*);
4. writes `4114030/teamkit.cfg` (`set name "value"` lines, then `perso.cfg`);
5. kills leftovers of a hard stop (`wineserver -k`, an old log reader);
6. starts `wine DedicatedServer.exe cli=1 config=teamkit.cfg` and copies the game log into the AMP
   console: **the server writes nothing to stdout**, only to `Documents/The Riftbreaker/exor_logs.txt`
   (rotated by the game to `exor_logs.1.txt`…`.3.txt` at each start). ~110 lines of graphics
   settings and headless warnings are hidden, as are the mission scripts' `[LUA …]` lines (except
   errors); the full log stays in `donnees/`;
7. prints `TeamKit : The Riftbreaker pret, il ecoute sur le port 6321 en UDP.` once the network is up
   (`[NetServerGNS] running as: ip:`) **and** the map is loaded (first autosave or first pause);
8. watchdog: if the game sits in `MenuState` for 60 s without listening (that is what it does with an
   unknown `mission_save` or an incomplete config: it waits for a menu that does not exist), or is not
   ready after 3 minutes, it says so in French and stops with exit code 1;
9. on SIGTERM (AMP stop): `wineserver -k`, exit 0.

**There is no clean stop.** The server reads no console input (commands on stdin are ignored:
tested), has no window to close (`wine taskkill` without `/F` finds nothing) and no quit command.
A stop or restart goes back to the **last save** (see *Saves and resume*: that may be the last
start). `server_pause_game_when_empty` (on by default) freezes the world when nobody is connected.

### Text values

Values are written between straight double quotes. Tested in a real save file: accents, `—`, `//`,
`\`, `;` and apostrophes are kept as typed. A straight `"` would end the value: the script turns it
into `'`. Control characters are removed.

## Settings exposed in AMP (French UI)

| AMP setting | Game key | Default |
|---|---|---|
| Nom du serveur | `server_name` | French TeamKit name with the Discord link |
| Mot de passe des joueurs | `server_password` | empty |
| Joueurs maximum (1–4) | `server_max_players_count` | 4 (EXOR: officially supported maximum) |
| Mode de jeu | `campaign` | Open Campaign (`open/open`); also `mp_story/mp_story`, `mp_survival/mp_survival` |
| Biome | `mission` | desert → `campaigns/open/headquarters_desert` or `survival/desert`; ignored in Story |
| Difficulté | `difficulty` | normal → `normal` / `coop_campaign_normal` / `coop_normal` |
| Au démarrage | `mission_save` | resume the latest save |
| Nom de la sauvegarde à charger | `mission_save` | empty |
| Pause quand le serveur est vide | `server_pause_game_when_empty` | on |
| Sauvegarde automatique toutes les | `autosave_timer` (minutes) | 5 (game default 10) |
| Mot de passe RCON | `server_rcon_password` | empty (RCON off) |

Mission and difficulty names are the lists of EXOR's guide. `magma` and `swamp_lakes` exist only in
Survival; the script refuses them in Open Campaign. Forced lines: `app_mode "server"`,
`disable_steam "1"`, `server_broadcast_enabled "0"`. Any other variable goes in `perso.cfg`.

## Saves and resume

With a `campaign` line, **every start creates a new campaign**: progress only comes back through
`mission_save "<save name>"`. A save is `donnees/campaignV2/<id>.campaign/<name in base64>.cs`
(+ `.inf`, `.pic`) and `<id>_<date>.map/`. Its name is the file name decoded, e.g.
`Autosave: 2026.10.10 - 17:36`; the `.inf` holds the campaign type (`campaigns/open/open.campaign`,
`campaigns/mp_story/mp_story.campaign`, `campaigns/mp_survival/mp_survival.campaign`) and, in
Survival, the map (`missions/survival/jungle.mission`).

*Au démarrage* = **Reprendre** (default): the script loads the most recent save of the same mode (and
same map in Survival), or starts a new game if there is none. **Nouvelle partie** creates a new one
at every start (to use once, then switch back). **Sauvegarde nommée** loads the given name; an unknown
name is refused before starting (the game would hang in its menu). The console shows which save was
loaded. Only the server saves in a dedicated game (EXOR changelog: "only the server can save the game").

**The game keeps only a few autosaves per server name** (seen on 10 Oct 2026:
`Removing autosave, campaign id <server name> save name Autosave: …`, the 5th autosave removed the
oldest, which belonged to *another mode*). The campaign folder is shared by every mode played under
the same server name. So switching modes and coming back later does **not** reliably find the old
game: after a few starts in the other mode, its saves are gone. Pick one mode per instance (or,
untested, a different server name per mode). AMP backups of `donnees/` are the safety net.

**When the game saves.** Observed: at every map load, i.e. **at every start** (EXOR changelog:
"Loading into a map will now trigger an autosave in multiplayer") and on map changes. **No periodic
autosave was seen**: 8 minutes of unpaused play with a connected client and `autosave_timer "5"`,
then 3 minutes with `autosave_timer "1"` (+ `autosave_timer_debug "1"`), produced no save. The
setting is kept (the game reads it: `autosave_timer : 1` in its log) but may only apply with a real
player or a server owner. Until checked with real players: **a stop or restart can lose the whole
session since the last start or map change** — restart only when nobody plays, and do not
schedule frequent restarts. The engine has a `save_game` console command (strings of the binary):
`rcon save_game` from a player's console is worth trying before a planned stop (untested).

## Console and players

- The AMP console **cannot send commands** to the game (`HasWriteableConsole=False`).
  Admin is RCON from a player's game: open the console, type `server_rcon_password <password>`,
  then `rcon <command>` (EXOR's example: `rcon cheat_god_mode 1`).
- **No player list in AMP** (`App.MaxUsers=0`). The game logs arrivals
  (`ServerGameplayState: Player '0':'Name':':{GUID}'!`, the script adds
  `TeamKit : Name a rejoint la partie.`) but **nothing when a player leaves**: after a client was
  killed, the only line 25 s later was `GameplayState::PauseGame` (server empty). The same pause line
  also appears while any player is loading in, so it cannot be used to count players. A list that
  only grows would be wrong; there is none.

## How players join

Not listed anywhere: players need the server IP. Two ways exist in the game:

- the in-game console: `connect "<IP>"` (community image documentation);
- the server browser has a *join with link* popup (`gui/popup/join_with_link`, `connect_with_link`
  in the binary).

What was tested: the game's own client code, started headless with
`launch_activity=connect;127.0.0.1 disable_steam=1`, joined the server and played (logged as
`Player '0':'Testeur'`). A normal Steam copy of the game was **not** tested: the community image notes
that a client may get `invalid server identity` and then needs `set disable_steam "1"` in
`Documents/The Riftbreaker/config/developer.cfg`. To be checked with a real player first.

## Resources (measured, 10 Oct 2026)

| | |
|---|---|
| RAM | 1.2–1.5 GB idle with a map loaded, 1.65 GB with one connected client (resident memory of `DedicatedServer.exe`) → plan **3 GB** for 4 players |
| Disk | 667 MB server + 1.4 GB Wine prefix + 5–9 MB per save (a few kept) → **~2.2 GB** |
| Start | 6–16 s to ready (new map: ~10 s generation); prefix creation 11 s once |
| CPU | low when paused; EXOR: "the only things you need to care about are the CPU and RAM" |

## Not tested

- A real Steam copy of the game joining over the Internet (only the game's own client, headless,
  over `127.0.0.1`), and the `developer.cfg` workaround.
- Periodic autosave during a real session, and `rcon save_game`.
- RCON, a password-protected join, 4 players at once, and AMP itself (Update, template rendering,
  console) — the first AMP install is the real test.

## Before pushing

```
python verifier.py
```

Must print `Tout est bon.`: JSON, includes, port, complete `Console.*` / `Limits.*` block, Wine image,
settings ↔ model ↔ script keys, offered choices ↔ accepted values ↔ EXOR's lists, download URLs,
LF/ASCII, `bash -n`, then 19 runs of the **real script** under bash (Wine stubbed): default and tricky
values read back like the game reads them, save selection on fake saves, refusals; the log filter on
real server lines; console regexes.

## Install in AMP

ADS → Configuration → Instance Deployment → **Configuration Repositories**: add
`hydrocut/AMPTemplates-Riftbreaker:main`, save, **Fetch latest**. Create Instance →
**The Riftbreaker (TeamKit)**, port **6321 UDP** → **Update** (must end with
`TeamKit : serveur dedie installe, build Steam …`) → **Start**.

## Sources

- EXOR Studios, *Dedicated Server Setup Guide* (exorstudios.com/blog/rb-dedicated-setup, Steam
  announcement of 23 Apr 2026): `cli=1 config=config.cfg`, every config key, modes, missions, difficulties, RCON.
- EXOR Studios, *Dedicated Server – Progress Report* (21 Nov 2025) and *Dedicated Server Experimental
  Release* (11 Dec 2025): anonymous SteamCMD, headless, versions must match, Linux untested.
- api.steamcmd.net `/v1/info/4114030`: Tool, free to download, depots, `DedicatedServer.bat`.
- j3n5-group/riftbreaker-docker (GitLab): Wine + SteamCMD layout, `exor_logs.txt`, LAN vs Steam mode, client `connect`.
- Skywardhigh/Riftbreaker-AMPTemplate (GitHub): Windows AMP template, join line, `disable_steam=1`.
- CubeCoders AMPTemplates: `windrose`, `star-rupture`, `empyrion-galactic-survival`, `foundry` (Wine image, SteamCMD `ForceDownloadPlatform`).

## Credits

The Riftbreaker is © EXOR Studios. This repository only contains the template; the server is
downloaded from Steam by SteamCMD.

---

## Résumé en français

Template AMP pour le **serveur dédié officiel de The Riftbreaker** (outil Steam gratuit 4114030,
téléchargé **sans compte Steam**), pour jouer à **4 au plus en coopération** : campagne ouverte,
campagne histoire ou survie. **Le jeu est payant** : chaque joueur doit l'avoir sur Steam, **dans la
même version que le serveur** (faire Update après chaque mise à jour du jeu).

- **Serveur Windows seulement** : il tourne sous **Wine** dans le conteneur
  `cubecoders/ampbase:wine-stable` (obligatoire), sans affichage, sans rien installer de plus.
- **Connexion par adresse IP seulement** : le mode Steam (liste des serveurs du jeu) se bloque sous
  Wine. Le serveur n'apparaît dans aucune liste ; les joueurs tapent l'IP dans le jeu.
- **Un seul port, 6321 en UDP, impossible à changer** : une seule instance Riftbreaker par adresse IP.
- **Réglages en français** : nom (TeamKit + Discord par défaut), mot de passe, joueurs (1 à 4), mode,
  biome, difficulté, reprise, pause quand vide, sauvegarde auto, mot de passe RCON.
- **Reprise automatique** de la dernière sauvegarde du même mode ; sinon le jeu recommencerait une
  partie neuve à chaque démarrage. Le jeu ne garde que quelques sauvegardes automatiques par nom de
  serveur, tous modes confondus : un mode par instance.
- **Pas d'arrêt propre** (le jeu n'a ni console ni commande d'arrêt) et **aucune sauvegarde
  périodique observée** : le jeu sauvegarde à chaque chargement de carte (donc à chaque démarrage).
  Un arrêt peut perdre la session en cours : ne redémarrer que quand personne ne joue.
- **Pas de liste de joueurs** dans AMP (le jeu n'écrit pas les départs).
- **Testé en vrai** le 10 oct. 2026 dans un conteneur jetable : 1,2 à 1,65 Go de RAM, prêt en 6 à 16 s,
  un client (le jeu lui-même, sans affichage) s'est connecté par IP.
- Avant de pousser : `python verifier.py` doit répondre « Tout est bon. ».
