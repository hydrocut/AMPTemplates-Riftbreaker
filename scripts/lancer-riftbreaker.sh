#!/bin/bash
# lancer-riftbreaker.sh - pose par le template AMP TeamKit (recree a chaque Update).
#
#   lancer-riftbreaker.sh preparer   etape d'Update : prefixe Wine, dossier des sauvegardes
#   lancer-riftbreaker.sh <port>     demarrage du serveur (ligne de commande d'AMP)
#
# Le serveur dedie de The Riftbreaker n'existe qu'en version Windows : il tourne ici
# sous Wine (image cubecoders/ampbase:wine-stable), sans affichage ni Xvfb.
# Ce script :
#  1. lit les reglages qu'AMP ecrit dans 4114030/reglages-amp.txt et les controle ;
#  2. choisit la partie : reprise de la derniere sauvegarde du meme mode, nouvelle
#     partie, ou sauvegarde nommee ;
#  3. ecrit 4114030/teamkit.cfg (le fichier que lit le jeu avec config=teamkit.cfg) ;
#  4. lance le jeu et recopie son journal (exor_logs.txt) dans la console d'AMP :
#     le jeu n'ecrit rien sur sa sortie standard ;
#  5. ecrit la ligne "pret" quand la partie est chargee, et un message clair si
#     le jeu reste bloque (sauvegarde introuvable : il attend un menu qui n'existe pas) ;
#  6. a l'arret demande par AMP (SIGTERM), coupe Wine : le jeu n'a ni console ni
#     commande d'arret, la partie reprend a la derniere sauvegarde automatique.
cd "$(dirname "$0")" || exit 1
ICI="$PWD"
JEU="$ICI/4114030"
BIN="$JEU/bin/DedicatedServer.exe"
REGLAGES="$JEU/reglages-amp.txt"
CFG_NOM="teamkit.cfg"
PERSO="$ICI/perso.cfg"
DONNEES="$ICI/donnees"
LOGJEU="$DONNEES/exor_logs.txt"
PORT_JEU=6321

export WINEPREFIX="$ICI/.wine" WINEARCH=win64 WINEDEBUG=-all
export LANG=C.UTF-8 LC_ALL=C.UTF-8
# Comme DedicatedServer.bat fourni par Steam : aucune variable Steam pour le jeu.
unset DISPLAY SteamAppId SteamGameId SteamOverlayGameId STEAMAPPID

manque_jeu() {
  echo "ERREUR : $BIN introuvable. Lance Update : SteamCMD telecharge le serveur (app 4114030, sans compte Steam)."
}

# Le jeu range ses sauvegardes, son profil et son journal dans "Documents/The Riftbreaker"
# du profil Wine. Ce dossier devient un lien vers donnees/ : les sauvegardes restent dans
# le dossier de l'instance (sauvegardes AMP), meme si Wine relie Documents ailleurs.
lier_donnees() {
  mkdir -p "$DONNEES" || return 1
  local u="" d
  for d in "$WINEPREFIX/drive_c/users/$(id -un 2>/dev/null)" "$WINEPREFIX"/drive_c/users/*; do
    if [ -d "$d" ] && [ "$(basename "$d")" != "Public" ]; then u="$d"; break; fi
  done
  if [ -z "$u" ]; then
    echo "ERREUR : profil Wine introuvable dans $WINEPREFIX/drive_c/users/ : lance Update."
    return 1
  fi
  if [ -L "$u/Documents" ]; then
    rm -f "$u/Documents"
  fi
  mkdir -p "$u/Documents" || return 1
  local lien="$u/Documents/The Riftbreaker"
  if [ -L "$lien" ]; then
    [ "$(readlink "$lien")" = "$DONNEES" ] && return 0
    rm -f "$lien"
  elif [ -d "$lien" ]; then
    cp -a -n "$lien/." "$DONNEES/" && rm -rf "$lien" || {
      echo "ERREUR : impossible de deplacer $lien vers donnees/."
      return 1
    }
    echo "TeamKit : sauvegardes existantes deplacees dans donnees/."
  fi
  ln -s "$DONNEES" "$lien"
}

# Journal du jeu -> console d'AMP. On retire le bruit du demarrage (une centaine de
# lignes de reglages graphiques, avertissements d'interface sans ecran) et le nom du
# fichier source ; on y repere les etapes utiles.
lire_journal() {
  local l pret=0
  while IFS= read -r l; do
    l="${l%$'\r'}"
    case "$l" in
      *"SignInState.cpp:118 -"*|*"Framework.cpp:5"[0-9][0-9]" -"*|*NavigationGraph.cpp*|*MouseCursorPlugin.cpp*|\
      *"ConfigVarRegistry.cpp:88 - Warning: accessing undefined"*|*"Supported formats:"*|*"FreeImage"*|\
      *"Console command already registered"*|*TheoraFrameQueue.cpp*|*TheoraVideoClip*|*GuiMovie.cpp*|\
      *"No supported video modes detected"*|*"modio: ERROR"*|*"SteamGameServer_Init failed"*|*AudioManager.cpp*|\
      *RenderingState.cpp*|*"Invalid texture path"*|*"mounting external content"*|*"[VFS] mounting"*|\
      *TechniqueGenerator*|*" - *-*-* "*|*"DDS codec"*|*"Theora workers"*|*"Installing plugin"*|\
      *"Plugin successfully installed"*|*"Config variables:"*|*"Creating team relation"*|*"SignIn: User status"*|\
      *"Sound is disabled"*|*"Audio submix"*|*"OnStartupLogosFinishedEvent"*|*"Entering SignInState"*)
        continue ;;
      *"[LUA '"*)
        # Les scripts de mission ecrivent sans arret pendant la partie : on ne garde que les erreurs.
        case "$l" in *[Ee][Rr][Rr][Oo][Rr]*) ;; *) continue ;; esac ;;
    esac
    if [[ "$l" =~ ^(\[[0-9:.]+\]\ \[[a-z]+\])\ [A-Za-z0-9_]+\.(cpp|hpp|h):[0-9]+\ -\ (.*)$ ]]; then
      printf '%s %s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[3]}"
    else
      printf '%s\n' "$l"
    fi
    case "$l" in
      *"[NetServerGNS] running as: ip:"*) : > "$ETAT/ecoute" ;;
      *"activating: MenuState"*) : > "$ETAT/menu" ;;
      *"ServerGameplayState: Player '"*)
        if [[ "$l" =~ ServerGameplayState:\ Player\ \'[0-9]+\':\'(.*)\':\'[^\']*\'!$ ]]; then
          echo "TeamKit : ${BASH_REMATCH[1]} a rejoint la partie."
        fi ;;
    esac
    if [ "$pret" = 0 ] && [ -e "$ETAT/ecoute" ]; then
      case "$l" in
        *"StoreCampaignSave chain execution"*|*"GameplayState::PauseGame"*)
          pret=1
          : > "$ETAT/pret"
          echo "TeamKit : The Riftbreaker pret, il ecoute sur le port $PORT_JEU en UDP." ;;
      esac
    fi
  done
}
# Utilise par verifier.py : passe un journal du jeu (entree standard) dans le filtre.
if [ "$1" = "filtre" ]; then
  ETAT=$(mktemp -d) || exit 1
  lire_journal
  rm -rf "$ETAT"
  exit 0
fi

if [ "$1" = "preparer" ]; then
  if [ ! -f "$BIN" ]; then
    manque_jeu
    exit 1
  fi
  if [ ! -f "$WINEPREFIX/system.reg" ]; then
    echo "TeamKit : creation du prefixe Wine (une minute environ, une seule fois)..."
    # mscoree / mshtml : pas de Mono ni de Gecko a telecharger, le jeu n'en a pas besoin.
    WINEDLLOVERRIDES="mscoree,mshtml=" timeout 300 wineboot --init > /dev/null 2>&1
    timeout 60 wineserver -w
    if [ ! -f "$WINEPREFIX/system.reg" ]; then
      echo "ERREUR : la creation du prefixe Wine a echoue. Cette instance doit tourner dans le conteneur cubecoders/ampbase:wine-stable."
      exit 1
    fi
  fi
  lier_donnees || exit 1
  echo "TeamKit : $(wine --version 2>/dev/null || echo 'Wine introuvable'), prefixe pret, sauvegardes dans donnees/campaignV2."
  build=$(sed -n 's/^[[:space:]]*"buildid"[[:space:]]*"\([0-9]*\)".*/\1/p' "$JEU/steamapps/appmanifest_4114030.acf" 2>/dev/null | head -n 1)
  echo "TeamKit : serveur dedie installe, build Steam ${build:-inconnu}. Les joueurs doivent avoir la meme version du jeu."
  exit 0
fi

# -- Demarrage ----------------------------------------------------------------
refuser() {
  echo "ERREUR : $1"
  echo "Corrige ce reglage dans l'onglet Configuration d'AMP, puis relance."
  exit 1
}

PORT="${1:-$PORT_JEU}"
if [ "$PORT" != "$PORT_JEU" ]; then
  refuser "le port du jeu doit etre $PORT_JEU (UDP). The Riftbreaker ne sait pas en changer et les joueurs s'y connectent toujours. Port actuel dans AMP : $PORT."
fi
[ -f "$BIN" ] || { manque_jeu; exit 1; }
[ -f "$REGLAGES" ] || { echo "ERREUR : $REGLAGES absent. AMP l'ecrit au demarrage a partir de AMP_reglages.txt : lance Update."; exit 1; }
command -v wine > /dev/null || { echo "ERREUR : Wine absent. Cette instance doit tourner dans le conteneur cubecoders/ampbase:wine-stable."; exit 1; }
[ -f "$WINEPREFIX/system.reg" ] || { echo "ERREUR : prefixe Wine absent : lance Update."; exit 1; }

declare -A R
while IFS= read -r ligne || [ -n "$ligne" ]; do
  ligne="${ligne%$'\r'}"
  case "$ligne" in
    \#*|'') ;;
    *=*) R["${ligne%%=*}"]="${ligne#*=}" ;;
  esac
done < "$REGLAGES"

# Texte libre ecrit entre guillemets droits dans le .cfg : un " fermerait la valeur.
# Accents, tiret long, //, \, ; et apostrophe passent tels quels (essai du 10/10/2026).
texte() {
  local q="'"
  local v="${1//\"/$q}"
  printf '%s' "$v" | tr -d '\000-\037\177'
}

NOM=$(texte "${R[nom]}")
MDP=$(texte "${R[motdepasse]}")
RCON=$(texte "${R[rcon]}")
JOUEURS="${R[joueurs]:-4}"
MODE="${R[mode]:-open}"
BIOME="${R[biome]:-desert}"
NIVEAU="${R[difficulte]:-normal}"
DEMARRAGE="${R[demarrage]:-reprendre}"
SAUVEGARDE=$(texte "${R[sauvegarde]}")
PAUSE="${R[pause_vide]:-1}"
AUTOSAVE="${R[autosave]:-5}"

[ -n "$NOM" ] || NOM="Serveur TeamKit.fr"
[[ "$JOUEURS" =~ ^[1-4]$ ]] || refuser "joueurs maximum '$JOUEURS' : de 1 a 4 (4 est le maximum officiel)."
[[ "$NIVEAU" =~ ^(easy|normal|hard|brutal)$ ]] || refuser "difficulte '$NIVEAU' inconnue."
[[ "$DEMARRAGE" =~ ^(reprendre|nouvelle|sauvegarde)$ ]] || refuser "choix au demarrage '$DEMARRAGE' inconnu."
[[ "$PAUSE" =~ ^[01]$ ]] || refuser "pause quand le serveur est vide : '$PAUSE' (0 ou 1)."
[[ "$AUTOSAVE" =~ ^[0-9]+$ ]] && [ "$AUTOSAVE" -ge 1 ] && [ "$AUTOSAVE" -le 60 ] || refuser "sauvegarde automatique '$AUTOSAVE' : de 1 a 60 minutes."

# Mode -> lignes du jeu (guide officiel d'EXOR, "Dedicated Server Setup Guide", avril 2026).
case "$MODE" in
  open)
    [[ "$BIOME" =~ ^(jungle|metallic|acid|ice|swamp|caverns|desert)$ ]] \
      || refuser "le biome '$BIOME' n'existe pas en campagne ouverte (jungle, metallic, acid, ice, swamp, caverns, desert)."
    CAMPAGNE="open/open"; MISSION="campaigns/open/headquarters_$BIOME"; DIFF="$NIVEAU"
    MARQUE="campaigns/open/open.campaign"; MARQUE2=""
    LIBELLE="campagne ouverte, biome $BIOME, difficulte $NIVEAU" ;;
  story)
    CAMPAGNE="mp_story/mp_story"; MISSION=""; DIFF="coop_campaign_$NIVEAU"
    MARQUE="campaigns/mp_story/mp_story.campaign"; MARQUE2=""
    LIBELLE="campagne histoire, difficulte $NIVEAU" ;;
  survival)
    [[ "$BIOME" =~ ^(jungle|acid|desert|magma|ice|metallic|caverns|swamp|swamp_lakes)$ ]] \
      || refuser "le biome '$BIOME' n'existe pas en survie."
    CAMPAGNE="mp_survival/mp_survival"; MISSION="survival/$BIOME"; DIFF="coop_$NIVEAU"
    MARQUE="campaigns/mp_survival/mp_survival.campaign"; MARQUE2="missions/survival/$BIOME.mission"
    LIBELLE="survie, biome $BIOME, difficulte $NIVEAU" ;;
  *) refuser "mode de jeu '$MODE' inconnu (open, story, survival)." ;;
esac

lier_donnees || exit 1

# Nom d'une sauvegarde = nom de son fichier .cs, en base64 (ex. "Autosave: 2026.10.10 - 17:36").
nom_sauvegarde() {
  local b
  b=$(basename "$1" .cs)
  printf '%s' "$b" | tr '_-' '/+' | base64 -d 2>/dev/null | tr -d '\000-\037\177"'
}

# Derniere sauvegarde (la plus recente) dont le .inf porte le mode (et le biome en survie).
derniere_sauvegarde() {
  local f inf t tm=0 meilleur=""
  shopt -s nullglob
  for f in "$DONNEES"/campaignV2/*.campaign/*.cs; do
    inf="${f%.cs}.inf"
    [ -f "$inf" ] || continue
    grep -a -q -F "$MARQUE" "$inf" || continue
    [ -z "$MARQUE2" ] || grep -a -q -F "$MARQUE2" "$inf" || continue
    t=$(stat -c %Y "$f" 2>/dev/null) || continue
    if [ "$t" -gt "$tm" ]; then tm=$t; meilleur="$f"; fi
  done
  shopt -u nullglob
  [ -n "$meilleur" ] && nom_sauvegarde "$meilleur"
}

sauvegarde_existe() {
  local f
  shopt -s nullglob
  for f in "$DONNEES"/campaignV2/*.campaign/*.cs; do
    if [ "$(nom_sauvegarde "$f")" = "$1" ]; then shopt -u nullglob; return 0; fi
  done
  shopt -u nullglob
  return 1
}

CHARGER=""
case "$DEMARRAGE" in
  reprendre)
    CHARGER=$(derniere_sauvegarde)
    if [ -n "$CHARGER" ]; then
      echo "TeamKit : reprise de la derniere sauvegarde ($LIBELLE) : '$CHARGER'."
    else
      echo "TeamKit : aucune sauvegarde pour ce mode, nouvelle partie : $LIBELLE."
    fi ;;
  nouvelle)
    echo "TeamKit : NOUVELLE partie a chaque demarrage ($LIBELLE). Repasse 'Au demarrage' sur 'Reprendre' pour garder la progression." ;;
  sauvegarde)
    [ -n "$SAUVEGARDE" ] || refuser "'Au demarrage' = sauvegarde nommee, mais aucun nom de sauvegarde n'est donne."
    sauvegarde_existe "$SAUVEGARDE" || refuser "sauvegarde '$SAUVEGARDE' introuvable dans donnees/campaignV2 (le jeu resterait bloque au menu)."
    CHARGER="$SAUVEGARDE"
    echo "TeamKit : chargement de la sauvegarde '$CHARGER'." ;;
esac

{
  echo "// teamkit.cfg - ECRIT PAR lancer-riftbreaker.sh a chaque demarrage, depuis les reglages d'AMP."
  echo "// Ne le modifie pas : change les reglages dans AMP, ou ajoute tes lignes dans perso.cfg."
  echo "set app_mode \"server\""
  echo "set disable_steam \"1\""
  echo "set server_broadcast_enabled \"0\""
  echo "set server_name \"$NOM\""
  echo "set server_password \"$MDP\""
  echo "set server_rcon_password \"$RCON\""
  echo "set server_max_players_count \"$JOUEURS\""
  echo "set server_pause_game_when_empty \"$PAUSE\""
  echo "set autosave_timer \"$AUTOSAVE\""
  if [ -n "$CHARGER" ]; then
    echo "set mission_save \"$CHARGER\""
  else
    echo "set campaign \"$CAMPAGNE\""
    [ -z "$MISSION" ] || echo "set mission \"$MISSION\""
    echo "set difficulty \"$DIFF\""
  fi
  if [ -f "$PERSO" ]; then
    echo "// --- perso.cfg ---"
    tr -d '\r' < "$PERSO"
  fi
} > "$JEU/$CFG_NOM"

if [ ! -f "$PERSO" ]; then
  printf '%s\n' \
    "// perso.cfg - lignes en plus pour le serveur The Riftbreaker, une par ligne :" \
    "//   set nom_de_la_variable \"valeur\"" \
    "// Ajoute a la fin de teamkit.cfg a chaque demarrage. Le template ne l'ecrase jamais." \
    "// Les lignes qui commencent par // sont ignorees. Ne remets pas disable_steam a 0 :" \
    "// sous Wine, le mode Steam bloque le serveur au demarrage (essai du 10/10/2026)." > "$PERSO"
fi

# Utilise seulement par verifier.py : s'arrete apres avoir ecrit teamkit.cfg.
[ -z "$TK_ESSAI" ] || exit 0

# Restes d'un arret brutal (lanceur tue net) : Wine garderait le port, et l'ancien
# lecteur du journal recopierait chaque ligne une deuxieme fois (essai du 10/10/2026).
wineserver -k > /dev/null 2>&1
pkill -x -f "tail -n 0 -F $LOGJEU" 2> /dev/null

ETAT=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/riftbreaker.XXXXXX") || exit 1

# -n 0 : seulement ce que le jeu ecrit a partir de maintenant. Au demarrage, le jeu
# renomme l'ancien journal en exor_logs.1.txt (puis .2, .3) et en recommence un :
# tail -F suit le nouveau fichier depuis son debut.
( tail -n 0 -F "$LOGJEU" 2> /dev/null | lire_journal ) &
LECTEUR=$!

cd "$JEU/bin" || exit 1
echo "TeamKit : demarrage de DedicatedServer.exe cli=1 config=$CFG_NOM (Wine, sans affichage)."
wine DedicatedServer.exe cli=1 "config=$CFG_NOM" &
PID=$!

ARRET=0
arreter() {
  trap - TERM INT
  ARRET=1
  echo "TeamKit : arret demande, fermeture du serveur (la partie reprendra a la derniere sauvegarde)."
  wineserver -k > /dev/null 2>&1
}
trap arreter TERM INT

# Garde-fou : sans la ligne "pret" au bout de 3 minutes (1 minute s'il est reste au
# menu), le jeu est bloque : on le dit et on arrete, plutot qu'un serveur muet.
(
  for t in $(seq 1 180); do
    sleep 1
    [ -e "$ETAT/pret" ] && exit 0
    kill -0 "$PID" 2> /dev/null || exit 0
    if [ "$t" -ge 60 ] && [ -e "$ETAT/menu" ] && [ ! -e "$ETAT/ecoute" ]; then break; fi
  done
  if [ -e "$ETAT/menu" ] && [ ! -e "$ETAT/ecoute" ]; then
    echo "ERREUR : le jeu est reste au menu : il n'a pas pu lancer la partie (sauvegarde introuvable, ou mode / biome / difficulte refuses)."
    echo "  Mets 'Au demarrage' sur 'Nouvelle partie' pour un essai, et relis perso.cfg."
  else
    echo "ERREUR : le serveur n'est pas pret apres 3 minutes. Dernieres lignes dans donnees/exor_logs.txt."
  fi
  : > "$ETAT/echec"
  kill -TERM $$ 2> /dev/null
) &
GARDE=$!

wait "$PID"
CODE=$?
while kill -0 "$PID" 2> /dev/null; do
  wait "$PID"
  CODE=$?
done
wineserver -k > /dev/null 2>&1
sleep 1
kill "$GARDE" 2> /dev/null
pkill -P "$LECTEUR" 2> /dev/null
kill "$LECTEUR" 2> /dev/null
if [ -e "$ETAT/echec" ]; then
  CODE=1
elif [ "$ARRET" = 1 ]; then
  CODE=0
fi
rm -rf "$ETAT"
exit "$CODE"
