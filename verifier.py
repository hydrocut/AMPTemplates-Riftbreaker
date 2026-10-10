# -*- coding: utf-8 -*-
"""
Contrôle du template avant de le pousser (même rôle que ceux de Wesnoth et Dominions 6).

    python verifier.py

1. tous les JSON se parsent ;
2. le .kvp : fichiers inclus, Ref du port, bloc Console.* / Limits.* complet, image Wine,
   conteneur obligatoire, SteamCMD anonyme, console en lecture seule, même dépôt que le manifest ;
3. le port : un seul, 6321 en UDP, le même que celui que le lanceur exige ;
4. chaque réglage exposé dans AMP est dans le modèle scripts/AMP_reglages.txt (rendu par AMP en
   reglages-amp.txt), chaque {{...}} du modèle a son réglage, et les clés du modèle sont
   exactement celles que lit le lanceur ;
5. les choix proposés (mode, biome, difficulté, démarrage, case à cocher, bornes des nombres)
   sont ceux qu'accepte le lanceur ; les biomes sont ceux du guide officiel d'EXOR ;
6. les fichiers téléchargés à l'Update existent dans scripts/, à l'URL du dépôt du manifest ;
   l'étape SteamCMD prend l'app 4114030 en version Windows ;
7. le lanceur : LF, ASCII, aucun {{, `bash -n` ;
8. aller-retour par le VRAI lanceur sous bash (Wine remplacé par des bouchons) : rendu des
   réglages comme AMP (remplacement brut), écriture de teamkit.cfg, relecture comme le jeu
   (set nom "valeur") ; valeurs par défaut et valeurs piégées (guillemet, accents, //, \\) ;
   choix de la sauvegarde à reprendre ; refus clairs ;
9. le filtre de journal du lanceur sur de vraies lignes du serveur (10/10/2026, build 22623747,
   « EXE: 1186 DATA: 847 ») : bruit retiré, ligne « prêt » une seule fois, arrivée d'un joueur ;
10. les regex de console.
"""
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ICI = os.path.dirname(os.path.abspath(__file__))
NOM = 'riftbreaker'
MODELE = 'scripts/AMP_reglages.txt'
LANCEUR = 'scripts/lancer-riftbreaker.sh'
soucis = []


def lire(nom, binaire=False):
    chemin = os.path.join(ICI, nom)
    if binaire:
        with open(chemin, 'rb') as f:
            return f.read()
    with io.open(chemin, encoding='utf-8') as f:
        return f.read()


def ok(quoi, detail):
    print('ok   %-26s %s' % (quoi, detail))


def py(motif):
    # AMP est en C# : (?<nom>...) ; Python veut (?P<nom>...)
    return re.compile(motif.replace('(?<', '(?P<'))


# ── 1. JSON ──────────────────────────────────────────────────────────────────
data = {}
for nom in ('manifest.json', NOM + 'config.json', NOM + 'metaconfig.json', NOM + 'ports.json', NOM + 'updates.json'):
    try:
        data[nom] = json.loads(lire(nom))
        ok(nom, 'JSON valide')
    except Exception as e:
        soucis.append('%s : JSON invalide (%s)' % (nom, e))
if soucis:
    print('\n'.join('NON  ' + s for s in soucis))
    sys.exit(1)
config = data[NOM + 'config.json']
updates = data[NOM + 'updates.json']
ports = data[NOM + 'ports.json']
lanceur = lire(LANCEUR)
modele = lire(MODELE)

# ── 2. kvp ───────────────────────────────────────────────────────────────────
kvp = lire(NOM + '.kvp')
cles = dict(l.split('=', 1) for l in kvp.splitlines() if '=' in l)
for ref in re.findall(r'@IncludeJson\[([^\]]+)\]', kvp):
    if not os.path.isfile(os.path.join(ICI, ref)):
        soucis.append('@IncludeJson[%s] : fichier absent' % ref)
for cle in ('Meta.ConfigManifest', 'Meta.MetaConfigManifest'):
    if not os.path.isfile(os.path.join(ICI, cles.get(cle, '?'))):
        soucis.append('%s pointe sur un fichier absent' % cle)
ATTENDUES = ['App.SupportsUniversalSleep', 'App.WakeupMode', 'App.ApplicationReadyMode', 'Console.FilterMatchRegex',
             'Console.FilterMatchReplacement', 'Console.ThrowawayMessageRegex', 'Console.AppReadyRegex',
             'Console.UserJoinRegex', 'Console.UserLeaveRegex', 'Console.UserChatRegex', 'Console.UpdateAvailableRegex',
             'Console.PreConnectRegex', 'Console.ConnectIPRegex', 'Console.MetricsRegex', 'Console.HideFromConsoleRegex',
             'Console.SuppressLogAtStart', 'Console.UserActions', 'Limits.SleepMode', 'Limits.SleepOnStart',
             'Limits.SleepDelayMinutes', 'Limits.DozeDelay', 'Limits.AutoRetryCount', 'Limits.SleepStartThresholdSeconds']
absentes = [c for c in ATTENDUES if c not in cles]
if absentes:
    soucis.append('clés absentes du .kvp : ' + ', '.join(absentes))
else:
    ok('kvp complet', 'les %d clés Console/Limits sont là' % len(ATTENDUES))
if cles.get('App.ApplicationReadyMode') == 'RegexMatch' and not cles.get('Console.AppReadyRegex'):
    soucis.append('RegexMatch sans AppReadyRegex : l’instance ne serait jamais déclarée prête')
ATTENDU_KVP = {
    'Meta.SpecificDockerImage': 'cubecoders/ampbase:wine-stable',  # serveur Windows seulement
    'Meta.ContainerPolicy': 'Required',
    'Meta.DockerRequired': 'True',
    'Meta.DisplayImageSource': 'steam:780310',
    'App.SteamUpdateAnonymousLogin': 'True',    # outil gratuit, téléchargement anonyme
    'App.SteamForceLoginPrompt': 'False',
    'App.ExecutableLinux': '/bin/bash',
    'App.ExitMethod': 'SIGTERM',                # le lanceur coupe Wine (pas de commande d'arrêt)
    'App.HasWriteableConsole': 'False',         # le jeu ne lit pas son entrée standard (essai)
    'App.HasReadableConsole': 'True',
    'App.MaxUsers': '0',                        # aucune ligne de départ de joueur dans le journal
    'App.BaseDirectory': './riftbreaker/4114030/',
    'App.RootDir': './riftbreaker/',
}
for cle, val in ATTENDU_KVP.items():
    if cles.get(cle) != val:
        soucis.append('%s devrait valoir %s (vaut %r)' % (cle, val, cles.get(cle)))
if cles.get('Meta.URL') != data['manifest.json']['url']:
    soucis.append('Meta.URL et manifest.json ne désignent pas le même dépôt')
if cles.get('App.UserJoinRegex') or cles.get('Console.UserJoinRegex') or cles.get('Console.UserLeaveRegex'):
    soucis.append('liste des joueurs : le jeu n’écrit aucun départ, une liste ne ferait que grossir')
cmd = cles.get('App.CommandLineArgs', '')
if cmd != '"{{$FullRootDir}}lancer-riftbreaker.sh" {{$GamePort}}':
    soucis.append('ligne de commande inattendue : %s' % cmd)
ok('kvp', 'Wine, conteneur obligatoire, SteamCMD anonyme, console en lecture')

# ── 3. port ──────────────────────────────────────────────────────────────────
m = re.search(r'^PORT_JEU=(\d+)$', lanceur, re.M)
if (len(ports) != 1 or ports[0]['Protocol'] != 'UDP' or ports[0]['Port'] != 6321 or not m
        or int(m.group(1)) != 6321 or ports[0]['Ref'] != cles.get('App.PrimaryApplicationPortRef')
        or '{{$%s}}' % ports[0]['Ref'] not in cmd):
    soucis.append('port : un seul, 6321/UDP, Ref principal, passé au lanceur qui exige PORT_JEU=6321')
else:
    ok('port', '6321/UDP, le même dans le lanceur')

# ── 4. réglages <-> modèle <-> lanceur ───────────────────────────────────────
champs = [c['FieldName'] for c in config]
par_nom = {c['FieldName']: c for c in config}
if len(champs) != len(set(champs)):
    soucis.append('réglages en double')
dans_modele = re.findall(r'\{\{([A-Za-z0-9_]+)\}\}', modele)
for c in config:
    if c['FieldName'] != c.get('ParamFieldName'):
        soucis.append('%s : FieldName et ParamFieldName différents' % c['FieldName'])
    if c.get('IncludeInCommandLine') is not False:
        soucis.append('%s : IncludeInCommandLine doit être false (réglage passé par le modèle)' % c['FieldName'])
    if dans_modele.count(c['FieldName']) != 1:
        soucis.append('{{%s}} doit apparaître une fois dans %s' % (c['FieldName'], MODELE))
for x in set(dans_modele) - set(champs):
    soucis.append('{{%s}} dans le modèle sans réglage dans AMP' % x)
cles_modele = {}
for l in modele.splitlines():
    if l.startswith('#') or not l.strip():
        continue
    r = re.fullmatch(r'([a-z_]+)=\{\{([A-Za-z0-9_]+)\}\}', l)
    if not r:
        soucis.append('ligne du modèle inattendue : %s' % l)
        continue
    cles_modele[r.group(1)] = r.group(2)
lues = set(re.findall(r'\$\{R\[(\w+)\]', lanceur))
if set(cles_modele) != lues:
    soucis.append('clés du modèle %s ≠ clés lues par le lanceur %s' % (sorted(cles_modele), sorted(lues)))
meta = data[NOM + 'metaconfig.json']
if (len(meta) != 1 or meta[0].get('ConfigType') != 'template' or meta[0].get('ConfigFile') != 'reglages-amp.txt'
        or meta[0].get('ConfigFileTemplate') != 'riftbreaker/AMP_reglages.txt'):
    soucis.append('metaconfig : template riftbreaker/AMP_reglages.txt -> reglages-amp.txt (dossier 4114030/)')
if 'REGLAGES="$JEU/reglages-amp.txt"' not in lanceur:
    soucis.append('le lanceur ne lit pas le fichier rendu par AMP (4114030/reglages-amp.txt)')
nom_defaut = par_nom['NomServeur']['DefaultValue']
if 'TeamKit.fr' not in nom_defaut or 'discord.gg/EuAjGMYPHY' not in nom_defaut:
    soucis.append('le nom du serveur par défaut doit citer TeamKit.fr et le Discord')
if not soucis:
    ok('réglages', '%d réglages, modèle et lanceur d’accord' % len(champs))


# ── 5. choix proposés <-> lanceur <-> guide d'EXOR ───────────────────────────
def motif(variable, apres=''):
    r = re.search(r'\[\[ "\$%s" =~ \^\(([a-z_|]+)\)\$ \]\]' % variable, lanceur[lanceur.find(apres):])
    return set(r.group(1).split('|')) if r else None


# Guide officiel « Dedicated Server Setup Guide » (EXOR, avril 2026) : listes des missions.
BIOMES_OUVERTE = {'jungle', 'metallic', 'acid', 'ice', 'swamp', 'caverns', 'desert'}
BIOMES_SURVIE = {'jungle', 'acid', 'desert', 'magma', 'ice', 'metallic', 'caverns', 'swamp', 'swamp_lakes'}
for champ, attendu in [('ModeJeu', {'open', 'story', 'survival'}), ('Difficulte', motif('NIVEAU')),
                       ('AuDemarrage', motif('DEMARRAGE')), ('Biome', BIOMES_OUVERTE | BIOMES_SURVIE)]:
    if set(par_nom[champ]['EnumValues']) != attendu:
        soucis.append('%s : AMP propose %s, attendu %s' % (champ, sorted(par_nom[champ]['EnumValues']), sorted(attendu or [])))
    if par_nom[champ]['DefaultValue'] not in par_nom[champ]['EnumValues']:
        soucis.append('%s : valeur par défaut hors liste' % champ)
if motif('BIOME', '  open)') != BIOMES_OUVERTE or motif('BIOME', '  survival)') != BIOMES_SURVIE:
    soucis.append('biomes acceptés par le lanceur ≠ guide d’EXOR')
if set(re.findall(r'^  (\w+)\)$', lanceur, re.M)) & {'open', 'story', 'survival'} != {'open', 'story', 'survival'}:
    soucis.append('le lanceur ne traite pas les trois modes')
if motif('NIVEAU') != {'easy', 'normal', 'hard', 'brutal'}:
    soucis.append('difficultés du lanceur ≠ guide d’EXOR (easy, normal, hard, brutal)')
if par_nom['PauseVide']['EnumValues'] != {'False': '0', 'True': '1'} or par_nom['PauseVide']['DefaultValue'] != '1':
    soucis.append('PauseVide : la case doit donner 0/1, cochée par défaut')
for champ, bornes in (('JoueursMax', ('1', '4')), ('SauvegardeAuto', ('1', '60'))):
    c = par_nom[champ]
    if (c['MinValue'], c['MaxValue']) != bornes:
        soucis.append('%s : bornes %s-%s, le lanceur accepte %s-%s' % (champ, c['MinValue'], c['MaxValue'], *bornes))
ok('choix', 'modes, biomes, difficultés, démarrage, bornes')

# ── 6. Update ────────────────────────────────────────────────────────────────
depot = data['manifest.json']['url'].replace('https://github.com/', '')
fetch = [e for e in updates if e['UpdateSource'] == 'FetchURL']
for e in fetch:
    attendu = 'https://raw.githubusercontent.com/%s/main/scripts/%s' % (depot, e['UpdateSourceArgs'])
    if e['UpdateSourceData'] != attendu:
        soucis.append('URL inattendue pour %s : %s' % (e['UpdateSourceArgs'], e['UpdateSourceData']))
    elif not os.path.isfile(os.path.join(ICI, 'scripts', e['UpdateSourceArgs'])):
        soucis.append('scripts/%s absent du dépôt' % e['UpdateSourceArgs'])
    elif e.get('UpdateSourceTarget') != '{{$FullRootDir}}' or e.get('OverwriteExistingFiles') is not True:
        soucis.append('%s : doit être réécrit dans {{$FullRootDir}} à chaque Update' % e['UpdateSourceArgs'])
if {e['UpdateSourceArgs'] for e in fetch} != {'AMP_reglages.txt', 'lancer-riftbreaker.sh'}:
    soucis.append('l’Update doit déposer AMP_reglages.txt et lancer-riftbreaker.sh')
st = [e for e in updates if e['UpdateSource'] == 'SteamCMD']
if (len(st) != 1 or st[0]['UpdateSourceData'] != '4114030' or st[0].get('ForceDownloadPlatform') != 'Windows'
        or updates[0] is not st[0]):
    soucis.append('étape SteamCMD : la première, app 4114030, ForceDownloadPlatform Windows')
if not any(e['UpdateSource'] == 'Executable' and e['UpdateSourceArgs'] == '"{{$FullRootDir}}lancer-riftbreaker.sh" preparer'
           and updates.index(e) == len(updates) - 1 for e in updates):
    soucis.append('la dernière étape doit être « lancer-riftbreaker.sh preparer »')
if not [s for s in soucis if 'Update' in s or 'URL' in s or 'SteamCMD' in s]:
    ok('Update', 'SteamCMD 4114030 (Windows), 2 fichiers du dépôt, préparation Wine')

# ── 7. lanceur ───────────────────────────────────────────────────────────────
for nom in (LANCEUR, MODELE):
    brut = lire(nom, binaire=True)
    if b'\r' in brut:
        soucis.append('%s : fins de ligne Windows (CRLF)' % nom)
if any(o > 127 for o in lire(LANCEUR, binaire=True)):
    soucis.append('%s : caractères non ASCII' % LANCEUR)
if '{{' in lanceur:
    soucis.append('le lanceur contient {{ : AMP pourrait le remplacer')
for besoin, pourquoi in [
    ('set disable_steam \\"1\\"', 'mode Steam bloqué sous Wine : IP directe imposée'),
    ('set app_mode \\"server\\"', 'sans app_mode server, le jeu attend un menu'),
    ('wine DedicatedServer.exe cli=1 "config=$CFG_NOM"', 'ligne de lancement du guide d’EXOR'),
    ('unset DISPLAY SteamAppId SteamGameId SteamOverlayGameId STEAMAPPID', 'comme DedicatedServer.bat'),
    ('wineserver -k', 'arrêt et nettoyage des restes de Wine'),
    ('trap arreter TERM INT', 'arrêt demandé par AMP'),
    ('tail -n 0 -F "$LOGJEU"', 'journal du jeu vers la console'),
]:
    if besoin not in lanceur:
        soucis.append('lanceur : %s (%s)' % (besoin, pourquoi))


def trouver_bash():
    for c in (r'C:\Program Files\Git\bin\bash.exe', r'C:\Program Files\Git\usr\bin\bash.exe', '/bin/bash'):
        if os.path.isfile(c):
            return c
    c = shutil.which('bash')
    if c and 'system32' not in c.lower():   # le bash de WSL ne verrait pas les chemins Windows
        return c
    return None


bash = trouver_bash()
if bash:
    r = subprocess.run([bash, '-n', os.path.join(ICI, LANCEUR)], capture_output=True, text=True)
    if r.returncode:
        soucis.append('bash -n : %s' % r.stderr.strip())
    else:
        ok('bash -n', LANCEUR)


# ── 8. aller-retour par le vrai lanceur ──────────────────────────────────────
def lire_cfg(texte):
    # Comme le jeu : « set nom "valeur" », // = commentaire en début de ligne ; le dernier gagne.
    v = {}
    for l in texte.splitlines():
        l = l.strip()
        if not l or l.startswith('//'):
            continue
        r = re.fullmatch(r'set (\w+) "([^"]*)"', l)
        if not r:
            raise ValueError('ligne illisible pour le jeu : %r' % l)
        v[r.group(1)] = r.group(2)
    return v


DEFAUTS = {c['FieldName']: str(c.get('DefaultValue', '')) for c in config}


def b64(nom):
    return base64.b64encode(nom.encode('utf-8')).decode('ascii')


def sauvegarde(dossier, campagne, nom, marques, age):
    d = os.path.join(dossier, 'donnees', 'campaignV2', '%s.campaign' % campagne)
    os.makedirs(d, exist_ok=True)
    cs = os.path.join(d, b64(nom) + '.cs')
    open(cs, 'wb').write(b'CMSI')
    open(os.path.join(d, b64(nom) + '.inf'), 'wb').write(b'CMSI\x00' + b'\x00'.join(m.encode() for m in marques) + b'\x00' + nom.encode())
    t = time.time() - age
    os.utime(cs, (t, t))


if not bash:
    print('---  aller-retour              bash introuvable : étape 8 sautée (à faire avant de pousser)')
else:
    with tempfile.TemporaryDirectory() as tmp:
        racine = os.path.join(tmp, 'riftbreaker')
        os.makedirs(os.path.join(racine, '4114030', 'bin'))
        os.makedirs(os.path.join(racine, '.wine', 'drive_c', 'users', 'amp'))
        open(os.path.join(racine, '.wine', 'system.reg'), 'w').close()
        open(os.path.join(racine, '4114030', 'bin', 'DedicatedServer.exe'), 'w').close()
        shutil.copy(os.path.join(ICI, LANCEUR), racine)
        bouchons = os.path.join(tmp, 'bouchons')
        os.makedirs(bouchons)
        for b in ('wine', 'wineserver'):
            with open(os.path.join(bouchons, b), 'w', newline='\n') as f:
                f.write('#!/bin/bash\nexit 0\n')
        env = dict(os.environ, TK_ESSAI='1', PATH=bouchons.replace('\\', '/') + os.pathsep + os.environ.get('PATH', ''))
        if os.name == 'nt':
            env['PATH'] = '/' + bouchons[0].lower() + bouchons[2:].replace('\\', '/') + ':' + '/usr/bin:/bin'
        lanceur_tmp = os.path.join(racine, 'lancer-riftbreaker.sh').replace('\\', '/')

        def lancer(change, port='6321'):
            v = dict(DEFAUTS, **change)
            t = modele
            for k, x in v.items():
                t = t.replace('{{%s}}' % k, x)       # AMP : remplacement brut
            with open(os.path.join(racine, '4114030', 'reglages-amp.txt'), 'w', encoding='utf-8', newline='\n') as f:
                f.write(t)
            cfg = os.path.join(racine, '4114030', 'teamkit.cfg')
            if os.path.exists(cfg):
                os.remove(cfg)
            p = subprocess.run([bash, lanceur_tmp, port], env=env, capture_output=True, timeout=60)
            sortie = p.stdout.decode('utf-8', 'replace') + p.stderr.decode('utf-8', 'replace')
            lu = lire_cfg(io.open(cfg, encoding='utf-8').read()) if os.path.exists(cfg) else None
            return p.returncode, sortie, lu

        n = 0

        def cas(titre, change, code_attendu, attendu=None, absent=(), dans_sortie=None, port='6321'):
            global n
            n += 1
            code, sortie, lu = lancer(change, port)
            if code != code_attendu:
                soucis.append('aller-retour « %s » : code %s au lieu de %s\n%s' % (titre, code, code_attendu, sortie))
                return
            if code_attendu == 1 and ('ERREUR' not in sortie or lu is not None):
                soucis.append('aller-retour « %s » : refus sans message clair, ou teamkit.cfg écrit quand même' % titre)
            for k, x in (attendu or {}).items():
                if lu is None or lu.get(k) != x:
                    soucis.append('aller-retour « %s » : %s = %r au lieu de %r' % (titre, k, None if lu is None else lu.get(k), x))
            for k in absent:
                if lu and k in lu:
                    soucis.append('aller-retour « %s » : %s ne devrait pas être écrit' % (titre, k))
            if dans_sortie and dans_sortie not in sortie:
                soucis.append('aller-retour « %s » : la console ne dit pas %r\n%s' % (titre, dans_sortie, sortie))

        BASE = {'app_mode': 'server', 'disable_steam': '1', 'server_broadcast_enabled': '0'}
        cas('défauts, aucune sauvegarde', {}, 0, dict(BASE, server_name=nom_defaut, server_password='', server_max_players_count='4',
            server_pause_game_when_empty='1', autosave_timer='5', campaign='open/open',
            mission='campaigns/open/headquarters_desert', difficulty='normal'), absent=['mission_save'],
            dans_sortie='nouvelle partie')
        cas('textes piégés', {'NomServeur': 'Héberg — "TeamKit" // a\\b ; l\'été', 'MotDePasse': 'mot de passe "x"',
                              'MotDePasseRcon': 'r,c;o#n'}, 0,
            {'server_name': "Héberg — 'TeamKit' // a\\b ; l'été", 'server_password': "mot de passe 'x'",
             'server_rcon_password': 'r,c;o#n'})
        cas('nom vide', {'NomServeur': ''}, 0, {'server_name': 'Serveur TeamKit.fr'})
        cas('histoire brutale', {'ModeJeu': 'story', 'Difficulte': 'brutal', 'Biome': 'magma'}, 0,
            {'campaign': 'mp_story/mp_story', 'difficulty': 'coop_campaign_brutal'}, absent=['mission'])
        cas('survie marais et lacs', {'ModeJeu': 'survival', 'Biome': 'swamp_lakes', 'Difficulte': 'easy'}, 0,
            {'campaign': 'mp_survival/mp_survival', 'mission': 'survival/swamp_lakes', 'difficulty': 'coop_easy'})
        cas('ouverte sans pause, 2 joueurs', {'Biome': 'ice', 'PauseVide': '0', 'JoueursMax': '2', 'SauvegardeAuto': '15'}, 0,
            {'mission': 'campaigns/open/headquarters_ice', 'server_pause_game_when_empty': '0',
             'server_max_players_count': '2', 'autosave_timer': '15'})
        cas('magma en campagne ouverte', {'Biome': 'magma'}, 1)
        cas('5 joueurs', {'JoueursMax': '5'}, 1)
        cas('sauvegarde auto à 0', {'SauvegardeAuto': '0'}, 1)
        cas('autre port', {}, 1, port='6400')
        cas('sauvegarde nommée vide', {'AuDemarrage': 'sauvegarde'}, 1)
        cas('sauvegarde nommée absente', {'AuDemarrage': 'sauvegarde', 'NomSauvegarde': 'Autosave: 2000.01.01 - 00:00'}, 1)
        # Sauvegardes : marques relevées dans de vrais .inf (10/10/2026).
        sauvegarde(racine, 111, 'Autosave: 2026.10.10 - 17:36',
                   ['missions/survival/jungle.mission', 'campaigns/mp_survival/mp_survival.campaign'], 3000)
        sauvegarde(racine, 111, 'Autosave: 2026.10.10 - 17:46',
                   ['missions/survival/jungle.mission', 'campaigns/mp_survival/mp_survival.campaign'], 2400)
        sauvegarde(racine, 222, 'Autosave: 2026.10.10 - 17:40',
                   ['missions/campaigns/open/headquarters_desert.mission', 'campaigns/open/open.campaign'], 2700)
        sauvegarde(racine, 333, 'Autosave: 2026.10.10 - 18:02',
                   ['missions/campaigns/story/headquarters.mission', 'campaigns/mp_story/mp_story.campaign'], 100)
        cas('reprise ouverte', {}, 0, dict(BASE, mission_save='Autosave: 2026.10.10 - 17:40'),
            absent=['campaign', 'mission', 'difficulty'], dans_sortie='reprise de la derniere sauvegarde')
        cas('reprise survie jungle (la plus récente)', {'ModeJeu': 'survival', 'Biome': 'jungle'}, 0,
            {'mission_save': 'Autosave: 2026.10.10 - 17:46'})
        cas('survie désert : autre carte, nouvelle partie', {'ModeJeu': 'survival', 'Biome': 'desert'}, 0,
            {'mission': 'survival/desert'}, absent=['mission_save'])
        cas('reprise histoire', {'ModeJeu': 'story'}, 0, {'mission_save': 'Autosave: 2026.10.10 - 18:02'})
        cas('nouvelle partie forcée', {'AuDemarrage': 'nouvelle'}, 0, {'campaign': 'open/open'}, absent=['mission_save'],
            dans_sortie='NOUVELLE partie')
        cas('sauvegarde nommée', {'AuDemarrage': 'sauvegarde', 'NomSauvegarde': 'Autosave: 2026.10.10 - 17:36'}, 0,
            {'mission_save': 'Autosave: 2026.10.10 - 17:36'})
        with open(os.path.join(racine, 'perso.cfg'), 'a', encoding='utf-8', newline='\n') as f:
            f.write('set server_vote_time "45"\n')
        cas('perso.cfg ajouté à la fin', {}, 0, {'server_vote_time': '45'})
        if not [s for s in soucis if s.startswith('aller-retour')]:
            ok('aller-retour', '%d cas par le vrai lanceur (bash), dont 6 refus' % n)

# ── 9. filtre de journal sur de vraies lignes (10/10/2026) ────────────────────
JOURNAL = r'''[17:35:47.176] [info] Windows.cpp:90 - STEAM: SteamGameServer_Init failed!
[17:35:47.178] [info]  - FreeImage version: 3.15.3
[17:35:47.279] [info] ConfigVarRegistry.cpp:88 - Warning: accessing undefined ConfigVariable: OnEnableEffect
[17:35:47.419] [info] Framework.cpp:534 -  * building(1)
[17:35:47.178] [info]  - *-*-* OGRE Initialising
[18:13:20.060] [info] VfsZipArchive.cpp:170 - [VFS] mounting: `Z:\srv\amp\riftbreaker\4114030\bin\..\packs\engine\00_win_engine.zip` as `/`
[18:13:20.038] [info] RiftbreakerApp.cpp:436 - ['dlc_1'] mounting external content: '' - '.'
[18:13:20.637] [info] DefaultSignIn.cpp:95 - SignIn: User status changed : 0. Name : User name : wine, user id:0, controller id : ControllerId( KEYBOARD, 0 )ControllerId( MOUSE, 0 )
[17:35:59.905] [info] LogService.cpp:71 - [LUA 'lua/missions/survival/survival_jungle.lua']: survival_jungle:init()
[17:35:47.423] [warning] CmdParser.cpp:14 - [WARNING] Console command already registered: refresh_gui_text_items
[17:35:47.940] [info] RiftbreakerApp.cpp:131 - The Riftbreaker EXE: 1186 DATA: 847
[17:35:47.944] [info] MouseCursorPlugin.cpp:194 - Invalid texture path: materials/textures/transparent.dds
[17:35:48.040] [info] SignInState.cpp:118 -  * autosave_timer : 5
[17:35:48.089] [warning] ExternalContentModio.cpp:41 - modio: ERROR[ 21250 ]='Invalid user'
[17:35:52.510] [info] ControllerState.cpp:521 - [ControllerState] activating: ServerGameplayState
[17:35:52.524] [info] NetServerGNS.cpp:173 - [NetServerGNS] listening for P2P connection as 'ip:::1'
[17:35:52.524] [info] NetServerGNS.cpp:182 - [NetServerGNS] running as: ip:[::]:6321
[17:35:52.878] [info] MapGenerator.cpp:373 - [MapGenerator]: mission file: `missions/survival/jungle.mission`
[17:35:57.948] [info] NavigationGraph.cpp:249 - NavigationGraph::Generate - Starting graph creation
[17:36:00.774] [info] GameplayState.cpp:978 - GenerateMap took: 8250 ms
[17:36:01.000] [info] SettingsMenuScreen.cpp:742 - ERROR: No supported video modes detected!
[17:36:01.042] [info] GameplayState.cpp:1650 - GameplayState::PauseGame
[17:36:03.393] [info] CampaignSaveManager.cpp:755 - Successfull StoreCampaignSave chain execution.
[17:57:40.777] [info] ServerGameplayState.cpp:1215 - ServerGameplayState: OnNetServerConnectReq ':{93160ECB-51F5-4A9E-977C-223AA7E29EF5}'!
[17:57:41.018] [info] ServerGameplayState.cpp:867 - ServerGameplayState: OnNetPlayerCreateRequest '0':'Testeur':':{93160ECB-51F5-4A9E-977C-223AA7E29EF5}' !
[17:57:43.193] [info] GameplayState.cpp:1650 - GameplayState::PauseGame
[17:58:05.175] [info] ServerGameplayState.cpp:966 - ServerGameplayState: Player '0':'Testeur':':{93160ECB-51F5-4A9E-977C-223AA7E29EF5}'!
[17:58:05.175] [info] GameplayState.cpp:1667 - GameplayState::ResumeGame
'''
ATTENDU_FILTRE = [
    '[17:35:47.940] [info] The Riftbreaker EXE: 1186 DATA: 847 ',
    '[17:35:52.510] [info] [ControllerState] activating: ServerGameplayState',
    "[17:35:52.524] [info] [NetServerGNS] listening for P2P connection as 'ip:::1'",
    '[17:35:52.524] [info] [NetServerGNS] running as: ip:[::]:6321',
    '[17:35:52.878] [info] [MapGenerator]: mission file: `missions/survival/jungle.mission`',
    '[17:36:00.774] [info] GenerateMap took: 8250 ms',
    '[17:36:01.042] [info] GameplayState::PauseGame',
    'TeamKit : The Riftbreaker pret, il ecoute sur le port 6321 en UDP.',
    '[17:36:03.393] [info] Successfull StoreCampaignSave chain execution.',
    "[17:57:40.777] [info] ServerGameplayState: OnNetServerConnectReq ':{93160ECB-51F5-4A9E-977C-223AA7E29EF5}'!",
    "[17:57:41.018] [info] ServerGameplayState: OnNetPlayerCreateRequest '0':'Testeur':':{93160ECB-51F5-4A9E-977C-223AA7E29EF5}' !",
    '[17:57:43.193] [info] GameplayState::PauseGame',
    "[17:58:05.175] [info] ServerGameplayState: Player '0':'Testeur':':{93160ECB-51F5-4A9E-977C-223AA7E29EF5}'!",
    'TeamKit : Testeur a rejoint la partie.',
    '[17:58:05.175] [info] GameplayState::ResumeGame',
]
if bash:
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(os.path.join(ICI, LANCEUR), tmp)
        p = subprocess.run([bash, os.path.join(tmp, 'lancer-riftbreaker.sh').replace('\\', '/'), 'filtre'],
                           input=JOURNAL.replace('\n', '\r\n').encode('utf-8'), capture_output=True, timeout=60)
        obtenu = [l.rstrip() for l in p.stdout.decode('utf-8').split('\n')[:-1]]
        if obtenu != [l.rstrip() for l in ATTENDU_FILTRE]:
            soucis.append('filtre du journal :\n       obtenu  %s\n       attendu %s\n%s'
                          % (obtenu, ATTENDU_FILTRE, p.stderr.decode('utf-8', 'replace')))
        else:
            ok('filtre du journal', '%d lignes réelles, %d gardées, « prêt » une fois, arrivée d’un joueur'
               % (JOURNAL.count('\n'), len(ATTENDU_FILTRE) - 2))

# ── 10. regex de console ─────────────────────────────────────────────────────
ESSAIS = [
    ('Console.AppReadyRegex', 'TeamKit : The Riftbreaker pret, il ecoute sur le port 6321 en UDP.', True),
    ('Console.AppReadyRegex', '[17:35:52.524] [info] [NetServerGNS] running as: ip:[::]:6321', False),
    ('Console.AppReadyRegex', 'TeamKit : demarrage de DedicatedServer.exe cli=1 config=teamkit.cfg (Wine, sans affichage).', False),
    ('Console.AppReadyRegex', 'ERREUR : le serveur n\'est pas pret apres 3 minutes. Dernieres lignes dans donnees/exor_logs.txt.', False),
]
for cle, ligne, attendu in ESSAIS:
    if bool(py(cles[cle]).search(ligne)) != attendu:
        soucis.append('%s %s : %s' % (cle, 'devrait reconnaître' if attendu else 'ne devrait pas reconnaître', ligne))
pret = re.search(r'echo "(TeamKit : The Riftbreaker pret[^"]*)"', lanceur)
if not pret or not py(cles['Console.AppReadyRegex']).search(pret.group(1).replace('$PORT_JEU', '6321')):
    soucis.append('la ligne « prêt » du lanceur ne correspond pas à Console.AppReadyRegex')
ok('console', '%d lignes testées' % len(ESSAIS))

print()
if soucis:
    print('%d problème(s) :' % len(soucis))
    print('\n'.join('  NON  ' + s for s in soucis))
    sys.exit(1)
print('Tout est bon.')
