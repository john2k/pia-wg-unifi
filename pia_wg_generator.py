#!/usr/bin/env python3
"""
PIA WireGuard Config Generator for UniFi UCG Fiber
Compatible with UCG Fiber 5.0.16 / UniFi Network 10.3.58

Usage: python pia_wg_generator.py
"""

import json
import sys
import os
import socket
import time
import base64
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------
def _check_deps():
    missing = []
    try:
        import requests  # noqa: F401
    except ImportError:
        missing.append("requests")
    try:
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey  # noqa: F401
    except ImportError:
        missing.append("cryptography")
    if missing:
        print("ERROR: missing libraries. Run:\n")
        print(f"  pip install {' '.join(missing)}\n")
        sys.exit(1)

_check_deps()

import requests
import urllib3
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PublicFormat, PrivateFormat, NoEncryption,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PIA_TOKEN_URL      = "https://www.privateinternetaccess.com/gtoken/generateToken"
PIA_SERVER_LIST_URL = "https://serverlist.piaservers.net/vpninfo/servers/v6"
WG_KEEPALIVE       = 25
WG_ALLOWED_IPS     = "0.0.0.0/0, ::/0"
LATENCY_TIMEOUT    = 2        # seconds per TCP probe
LATENCY_WORKERS    = 30       # concurrent probes
MAX_DISPLAY        = 20       # servers shown before "and N more"
LATENCY_PORT       = 443      # TCP port used to probe latency

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
SEP  = "=" * 64
SEP2 = "-" * 64


def banner(title: str):
    print(f"\n{SEP}\n  {title}\n{SEP}")


def info(msg: str):
    print(f"  [+] {msg}")


def step(msg: str):
    print(f"  [ ] {msg}", flush=True)


def err(msg: str):
    print(f"\n  [!] ERROR: {msg}\n")
    sys.exit(1)


def ask_int(prompt: str, lo: int, hi: int) -> int:
    while True:
        raw = input(prompt).strip()
        if raw.isdigit():
            val = int(raw)
            if lo <= val <= hi:
                return val
        print(f"      Entrez un nombre entre {lo} et {hi}.")


# ---------------------------------------------------------------------------
# WireGuard key generation
# ---------------------------------------------------------------------------
def generate_wg_keys() -> tuple[str, str]:
    """Return (private_key_b64, public_key_b64)."""
    priv = X25519PrivateKey.generate()
    priv_b = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub_b  = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(priv_b).decode(), base64.b64encode(pub_b).decode()


# ---------------------------------------------------------------------------
# PIA authentication
# ---------------------------------------------------------------------------
def get_pia_token(username: str, password: str) -> str:
    step("Authentification avec PIA...")
    try:
        r = requests.get(
            PIA_TOKEN_URL,
            auth=(username, password),
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        err(f"Connexion PIA impossible: {e}")

    if data.get("status") != "OK":
        err(f"Authentification refusee: {data.get('message', data)}")

    info("Authentification reussie!")
    return data["token"]


# ---------------------------------------------------------------------------
# Server list
# ---------------------------------------------------------------------------
def get_server_list() -> dict:
    step("Telechargement de la liste des serveurs PIA...")
    try:
        r = requests.get(PIA_SERVER_LIST_URL, timeout=20)
        r.raise_for_status()
        # Response = JSON blob + '\n\n' + signature — only parse the JSON part
        raw = r.text.split("\n\n")[0]
        data = json.loads(raw)
    except Exception as e:
        err(f"Impossible de recuperer la liste des serveurs: {e}")

    count = len(data.get("regions", []))
    info(f"{count} regions disponibles.")
    return data


def get_wg_port(server_data: dict) -> int:
    try:
        return int(server_data["groups"]["wg"][0]["ports"][0])
    except (KeyError, IndexError, TypeError):
        return 1337


# ---------------------------------------------------------------------------
# Region / country / province selection
# ---------------------------------------------------------------------------
def _build_country_map(regions: list) -> dict:
    """country -> list of region dicts."""
    countries: dict[str, list] = {}
    for r in regions:
        if not r.get("servers", {}).get("wg"):
            continue            # skip regions with no WG servers
        country = r.get("country", "??").upper()
        countries.setdefault(country, []).append(r)
    return dict(sorted(countries.items()))


# Map of ISO-2 country codes to full names for display
_COUNTRY_NAMES = {
    "AU": "Australie",        "AT": "Autriche",      "BE": "Belgique",
    "BR": "Bresil",           "CA": "Canada",         "CL": "Chili",
    "CZ": "Republique tcheque","DK": "Danemark",      "FI": "Finlande",
    "FR": "France",           "DE": "Allemagne",      "HK": "Hong Kong",
    "HU": "Hongrie",          "IN": "Inde",           "IE": "Irlande",
    "IL": "Israel",           "IT": "Italie",         "JP": "Japon",
    "MX": "Mexique",          "NL": "Pays-Bas",       "NZ": "Nouvelle-Zelande",
    "NO": "Norvege",          "PL": "Pologne",        "PT": "Portugal",
    "RO": "Roumanie",         "SG": "Singapour",      "ZA": "Afrique du Sud",
    "ES": "Espagne",          "SE": "Suede",          "CH": "Suisse",
    "UK": "Royaume-Uni",      "GB": "Royaume-Uni",    "US": "Etats-Unis",
    "AE": "Emirats arabes unis","AR": "Argentine",    "BA": "Bosnie",
    "BG": "Bulgarie",         "EE": "Estonie",        "GR": "Grece",
    "IS": "Islande",          "LV": "Lettonie",       "LT": "Lituanie",
    "LU": "Luxembourg",       "MK": "Macedoine du Nord","MD": "Moldavie",
    "AL": "Albanie",          "NG": "Nigeria",        "PH": "Philippines",
    "RS": "Serbie",           "SK": "Slovaquie",      "SI": "Slovenie",
    "TH": "Thailande",        "TW": "Taiwan",         "TR": "Turquie",
    "UA": "Ukraine",          "VN": "Vietnam",
}


def _country_display(code: str) -> str:
    return f"{_COUNTRY_NAMES.get(code, code)} ({code})"


def select_servers(regions: list) -> tuple[list, dict | None]:
    """
    Interactive 2-level menu: country -> region (or all regions).
    Returns (list_of_wg_servers, region_info_or_None).
    Each server dict gets '_region' injected.
    """
    country_map = _build_country_map(regions)
    country_codes = list(country_map.keys())

    # ---- Country filter ----
    banner("ETAPE 1 — Choisir le pays")
    filtre = input("  Filtrer par nom (laisser vide = tous): ").strip().lower()
    if filtre:
        filtered_codes = [
            c for c in country_codes
            if filtre in c.lower() or filtre in _COUNTRY_NAMES.get(c, "").lower()
        ]
    else:
        filtered_codes = country_codes

    if not filtered_codes:
        print("  Aucun pays correspondant. Recommencer.")
        return select_servers(regions)

    print()
    print(f"  {'#':<5} {'Pays':<35} {'Regions WG'}")
    print(f"  {SEP2}")
    for i, code in enumerate(filtered_codes, 1):
        nb = len(country_map[code])
        print(f"  {i:<5} {_country_display(code):<35} {nb}")

    choice_c = ask_int(f"\n  Selectionner [1-{len(filtered_codes)}]: ", 1, len(filtered_codes))
    selected_code = filtered_codes[choice_c - 1]
    country_regions = country_map[selected_code]

    # ---- Region selection ----
    banner(f"ETAPE 2 — Region dans {_country_display(selected_code)}")
    print(f"  {'#':<5} {'Region'}")
    print(f"  {SEP2}")
    print(f"  {'0':<5} Toutes les regions de ce pays")
    for i, reg in enumerate(country_regions, 1):
        print(f"  {i:<5} {reg.get('name', reg['id'])}")

    choice_r = ask_int(f"\n  Selectionner [0-{len(country_regions)}]: ", 0, len(country_regions))

    if choice_r == 0:
        servers = []
        for reg in country_regions:
            for srv in reg["servers"].get("wg", []):
                srv["_region"] = reg
                servers.append(srv)
        return servers, None
    else:
        reg = country_regions[choice_r - 1]
        servers = []
        for srv in reg["servers"].get("wg", []):
            srv["_region"] = reg
            servers.append(srv)
        return servers, reg


# ---------------------------------------------------------------------------
# Latency measurement
# ---------------------------------------------------------------------------
def _probe(ip: str, port: int) -> float:
    """TCP connect latency in ms, or inf on failure."""
    try:
        t0 = time.perf_counter()
        with socket.create_connection((ip, port), timeout=LATENCY_TIMEOUT):
            pass
        return round((time.perf_counter() - t0) * 1000, 1)
    except Exception:
        return float("inf")


def measure_all(servers: list, port: int) -> list:
    """Return servers list sorted by latency (field 'latency' added)."""
    total = len(servers)
    print(f"\n  [ ] Test de latence sur {total} serveurs (port TCP {port})...", flush=True)
    done = [0]

    def probe_one(srv):
        lat = _probe(srv["ip"], port)
        done[0] += 1
        pct = done[0] * 100 // total
        print(f"\r      {done[0]}/{total} ({pct}%)", end="", flush=True)
        return {**srv, "latency": lat}

    workers = min(LATENCY_WORKERS, total)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(probe_one, servers))

    print()  # newline after progress
    results.sort(key=lambda x: x["latency"])
    reachable = [s for s in results if s["latency"] != float("inf")]
    info(f"{len(reachable)}/{total} serveurs accessibles.")
    return results


# ---------------------------------------------------------------------------
# Server selection UI
# ---------------------------------------------------------------------------
def display_and_pick(servers: list) -> dict:
    reachable = [s for s in servers if s["latency"] != float("inf")]
    if not reachable:
        err("Aucun serveur accessible. Verifiez votre connexion Internet.")

    banner("ETAPE 3 — Choisir un serveur (tries par latence)")
    shown = reachable[:MAX_DISPLAY]

    print(f"\n  {'#':<5} {'Latence':<12} {'CN / Hostname':<40} {'IP':<18} {'Region'}")
    print(f"  {SEP2}")
    for i, srv in enumerate(shown, 1):
        lat_str = f"{srv['latency']:.1f} ms"
        reg_name = srv.get("_region", {}).get("name", "") if srv.get("_region") else ""
        print(f"  {i:<5} {lat_str:<12} {srv.get('cn', 'N/A'):<40} {srv['ip']:<18} {reg_name}")

    if len(reachable) > MAX_DISPLAY:
        print(f"\n  ... et {len(reachable) - MAX_DISPLAY} autres (top {MAX_DISPLAY} affiches)")

    choice = ask_int(f"\n  Selectionner [1-{len(shown)}]: ", 1, len(shown))
    selected = shown[choice - 1]
    info(
        f"Serveur choisi: {selected.get('cn')} ({selected['ip']}) "
        f"— {selected['latency']:.1f} ms"
    )
    return selected


# ---------------------------------------------------------------------------
# WireGuard key registration with PIA server
# ---------------------------------------------------------------------------
def register_wg_key(server_ip: str, wg_port: int, token: str, public_key: str) -> dict:
    step(f"Enregistrement de la cle WireGuard aupres de {server_ip}:{wg_port}...")
    url = f"https://{server_ip}:{wg_port}/addKey"
    try:
        r = requests.get(
            url,
            params={"pt": token, "pubkey": public_key},
            verify=False,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        err(f"Enregistrement impossible: {e}")

    if data.get("status") != "OK":
        err(f"Echec enregistrement: {data}")

    info("Cle enregistree avec succes!")
    return data


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------
def build_config(private_key: str, wg_data: dict, server: dict, region: dict | None) -> str:
    peer_ip     = wg_data.get("peer_ip", "")           # notre IP tunnel
    server_key  = wg_data.get("server_key", "")        # cle publique du serveur
    server_port = wg_data.get("server_port", 1337)
    dns_list    = wg_data.get("dns_servers", ["10.0.0.242"])
    dns         = ", ".join(dns_list) if isinstance(dns_list, list) else str(dns_list)

    server_ip   = server["ip"]
    server_cn   = server.get("cn", "pia-server")
    region_name = region.get("name", "PIA") if region else "PIA"
    ts          = datetime.now().strftime("%Y-%m-%d %H:%M")

    return (
        f"# PIA WireGuard — {region_name}\n"
        f"# Serveur : {server_cn} ({server_ip})\n"
        f"# Genere  : {ts}\n"
        f"# Importer dans UCG Fiber : Settings > VPN > WireGuard > Create New > Import Config\n"
        f"\n"
        f"[Interface]\n"
        f"PrivateKey = {private_key}\n"
        f"Address = {peer_ip}/32\n"
        f"DNS = {dns}\n"
        f"\n"
        f"[Peer]\n"
        f"PublicKey = {server_key}\n"
        f"Endpoint = {server_ip}:{server_port}\n"
        f"AllowedIPs = {WG_ALLOWED_IPS}\n"
        f"PersistentKeepalive = {WG_KEEPALIVE}\n"
    )


def save_config(content: str, server: dict, region: dict | None) -> str:
    region_name = region.get("name", "pia") if region else "pia"
    safe = re.sub(r"[^\w]", "_", region_name.lower())
    filename = f"pia_{safe}.conf"
    # Avoid overwriting
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(filename):
        filename = f"{base}_{counter}{ext}"
        counter += 1
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    return filename


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    banner("PIA WireGuard Config Generator — UCG Fiber")
    print("  Compatible UCG Fiber 5.0.16 / UniFi Network 10.3.58\n")

    # Credentials
    print("  Entrez vos identifiants PIA :")
    username = input("    Nom d'utilisateur : ").strip()
    password = input("    Mot de passe      : ")
    if not username or not password:
        err("Identifiants manquants.")

    # Generate WG keys early (no network needed)
    step("Generation des cles WireGuard...")
    private_key, public_key = generate_wg_keys()
    info("Cles generees.")

    # Auth
    token = get_pia_token(username, password)

    # Server list
    server_data = get_server_list()
    wg_port = get_wg_port(server_data)
    regions = server_data.get("regions", [])

    # Region picker
    servers, region_info = select_servers(regions)
    if not servers:
        err("Aucun serveur WireGuard pour cette selection.")

    # Latency
    sorted_servers = measure_all(servers, wg_port)

    # Server picker
    selected = display_and_pick(sorted_servers)
    selected_region = selected.get("_region") or region_info

    # Register key
    wg_data = register_wg_key(selected["ip"], wg_port, token, public_key)

    # Build config
    config_content = build_config(private_key, wg_data, selected, selected_region)

    # Preview
    banner("CONFIG GENEREE")
    print(config_content)

    # Save
    save_ans = input("  Sauvegarder le fichier .conf ? [O/n] : ").strip().lower()
    if save_ans not in ("n", "non"):
        filename = save_config(config_content, selected, selected_region)
        info(f"Fichier sauvegarde : {os.path.abspath(filename)}")
        print()
        print("  ┌─ COMMENT IMPORTER DANS UCG FIBER ──────────────────────────┐")
        print("  │  1. Ouvre UniFi Network (navigateur ou app)                │")
        print("  │  2. Settings > VPN > WireGuard                             │")
        print("  │  3. Clique « Create New » puis « Import Config »           │")
        print("  │  4. Selectionne le fichier .conf genere                    │")
        print("  │  5. Donne un nom au tunnel et sauvegarde                   │")
        print("  └────────────────────────────────────────────────────────────┘")
    else:
        info("Fichier non sauvegarde. Config affichee ci-dessus.")

    print()
    another = input("  Generer une autre config ? [o/N] : ").strip().lower()
    if another in ("o", "oui", "y", "yes"):
        main()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Annule par l'utilisateur.")
        sys.exit(0)
