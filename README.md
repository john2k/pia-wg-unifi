# pia-wg-unifi

Générateur interactif de configurations WireGuard pour **Private Internet Access (PIA)**, optimisé pour l'import direct dans un **UniFi UCG Fiber** (et tout équipement UniFi supportant WireGuard).

Sélection du pays/région, tri automatique par latence, génération du fichier `.conf` prêt à importer — le tout en ligne de commande, sans interface graphique, sans dépendance lourde.

---

## Fonctionnalités

- Authentification sécurisée avec l'API officielle PIA
- Téléchargement de la liste complète des serveurs PIA en temps réel
- Sélection interactive : pays → région (ou toutes les régions d'un pays)
- Test de latence TCP en parallèle sur tous les serveurs disponibles
- Classement automatique du plus rapide au plus lent
- Génération de la paire de clés WireGuard (Curve25519) localement
- Enregistrement de la clé publique auprès du serveur PIA choisi
- Export d'un fichier `.conf` standard WireGuard, importable directement dans UniFi Network
- Possibilité de générer plusieurs configs à la suite (plusieurs régions/serveurs)

---

## Compatibilité

| Équipement | Firmware | UniFi Network |
|---|---|---|
| UCG Fiber | 5.0.16 | 10.3.58 |
| UCG Ultra | 3.x+ | 9.x+ |
| UDM Pro / SE | tout | 8.x+ |
| UDM Base | tout | 8.x+ |

Tout équipement UniFi acceptant l'import de fichiers `.conf` WireGuard est supporté.

---

## Prérequis

- **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)  
  *(cocher "Add Python to PATH" lors de l'installation sur Windows)*
- Un abonnement **Private Internet Access** actif
- Connexion Internet

---

## Installation

### Windows (double-clic)

```
1. Télécharger ou cloner le dépôt
2. Double-cliquer sur  installer.bat
3. C'est tout
```

### Toutes plateformes (terminal)

```bash
git clone https://github.com/TON_USERNAME/pia-wg-unifi.git
cd pia-wg-unifi
pip install -r requirements.txt
```

---

## Utilisation

### Windows

```
Double-clic sur lancer.bat
```

### Terminal

```bash
python pia_wg_generator.py
```

---

## Déroulement étape par étape

```
================================================================
  PIA WireGuard Config Generator — UCG Fiber
================================================================
  Compatible UCG Fiber 5.0.16 / UniFi Network 10.3.58

  Entrez vos identifiants PIA :
    Nom d'utilisateur : p1234567
    Mot de passe      : ************

  [ ] Génération des clés WireGuard...
  [+] Clés générées.
  [ ] Authentification avec PIA...
  [+] Authentification réussie!
  [ ] Téléchargement de la liste des serveurs PIA...
  [+] 97 régions disponibles.

================================================================
  ÉTAPE 1 — Choisir le pays
================================================================
  Filtrer par nom (laisser vide = tous): canada

  #     Pays                                Régions WG
  ----------------------------------------------------------------
  1     Canada (CA)                         5

  Sélectionner [1-1]: 1

================================================================
  ÉTAPE 2 — Région dans Canada (CA)
================================================================
  #     Région
  ----------------------------------------------------------------
  0     Toutes les régions de ce pays
  1     CA Montreal
  2     CA Ontario
  3     CA Toronto
  4     CA Vancouver
  5     CA Alberta

  Sélectionner [0-5]: 0

  [ ] Test de latence sur 23 serveurs (port TCP 1337)...
      23/23 (100%)
  [+] 23/23 serveurs accessibles.

================================================================
  ÉTAPE 3 — Choisir un serveur (triés par latence)
================================================================

  #     Latence      CN / Hostname                            IP                 Région
  ----------------------------------------------------------------
  1     8.3 ms       ca-toronto404.privacy.network            185.216.x.x        CA Toronto
  2     9.1 ms       ca-toronto401.privacy.network            185.216.x.x        CA Toronto
  3     11.4 ms      ca-montreal401.privacy.network           104.200.x.x        CA Montreal
  4     14.7 ms      ca-ontario401.privacy.network            195.206.x.x        CA Ontario
  ...

  Sélectionner [1-20]: 1

  [+] Serveur choisi: ca-toronto404.privacy.network (185.216.x.x) — 8.3ms
  [ ] Enregistrement de la clé WireGuard...
  [+] Clé enregistrée avec succès!

================================================================
  CONFIG GÉNÉRÉE
================================================================
# PIA WireGuard — CA Toronto
# Serveur : ca-toronto404.privacy.network (185.216.x.x)

[Interface]
PrivateKey = <clé privée générée localement>
Address = 10.x.x.x/32
DNS = 10.0.0.242, 10.0.0.243

[Peer]
PublicKey = <clé publique du serveur PIA>
Endpoint = 185.216.x.x:1337
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25

  Sauvegarder le fichier .conf ? [O/n] : O
  [+] Fichier sauvegardé : pia_ca_toronto.conf
```

---

## Import dans UniFi Network (UCG Fiber)

1. Ouvre **UniFi Network** dans ton navigateur
2. Va dans **Settings → VPN → WireGuard**
3. Clique **Create New** puis **Import Config**
4. Sélectionne le fichier `.conf` généré
5. Donne un nom au tunnel (ex: `PIA Toronto`) et clique **Apply**

Le tunnel apparaît dans la liste VPN et peut être activé/désactivé à la volée.

Pour router tout le trafic d'un réseau local via le VPN, assigne le tunnel WireGuard comme gateway dans **Settings → Routing**.

---

## Structure du projet

```
pia-wg-unifi/
├── pia_wg_generator.py   # Script principal
├── requirements.txt      # Dépendances Python
├── installer.bat         # Installation des dépendances (Windows)
├── lancer.bat            # Raccourci de lancement (Windows)
└── README.md
```

---

## Comment ça fonctionne

```
┌─────────────────────────────────────────────────────────┐
│                     Ton ordinateur                      │
│                                                         │
│  1. Génère une paire de clés Curve25519 (WireGuard)    │
│  2. Authentifie avec l'API PIA → token temporaire      │
│  3. Télécharge la liste des serveurs PIA               │
│  4. Probe TCP en parallèle → tri par latence           │
│  5. POST /addKey sur le serveur choisi                 │
│     → reçoit : IP tunnel, clé publique serveur, DNS   │
│  6. Génère et sauvegarde le fichier .conf              │
└─────────────────────────────────────────────────────────┘
         ↓  import du .conf
┌─────────────────────────────────────────────────────────┐
│                    UCG Fiber                            │
│         Settings → VPN → WireGuard → Import            │
└─────────────────────────────────────────────────────────┘
         ↓  tunnel actif
┌─────────────────────────────────────────────────────────┐
│              Serveur PIA WireGuard                      │
│         Endpoint: <ip>:1337   Keepalive: 25s           │
└─────────────────────────────────────────────────────────┘
```

Les clés WireGuard sont générées **localement** — la clé privée ne quitte jamais ta machine. Seule la clé publique est envoyée à PIA pour l'enregistrement du tunnel.

---

## Dépendances

| Librairie | Usage |
|---|---|
| `requests` | Appels API PIA (auth, liste serveurs, enregistrement clé) |
| `cryptography` | Génération des clés WireGuard Curve25519 |

Tout le reste utilise la bibliothèque standard Python (`socket`, `concurrent.futures`, `base64`, etc.)

---

## Sécurité

- La **clé privée WireGuard** est générée localement et n'est jamais transmise
- Le **mot de passe PIA** est envoyé uniquement à `privateinternetaccess.com` via HTTPS
- Le **token d'authentification** est temporaire et utilisé une seule fois pour enregistrer la clé
- La connexion au serveur PIA pour l'enregistrement de la clé utilise HTTPS (SSL désactivé côté vérification car PIA utilise des certificats auto-signés sur ce endpoint — comportement identique aux scripts officiels PIA)

---

## Inspiré de

- [pia-foss/manual-connections](https://github.com/pia-foss/manual-connections) — scripts officiels PIA open source
- Documentation WireGuard : [wireguard.com](https://www.wireguard.com/)

---

## Licence

MIT — libre d'utilisation, de modification et de distribution.

> Ce projet n'est pas affilié à Private Internet Access ni à Ubiquiti/UniFi.
