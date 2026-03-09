#!/usr/bin/env python3
"""
orchestrator.py — Orchestratore Smart Playlists
================================================
Punto di ingresso unico: recupera tutti gli utenti Jellyfin,
per ognuno esegue tutti gli script di generazione playlist,
gestisce log e notifiche mail.

Installazione:
  sudo cp -r smartplaylists/ /usr/local/bin/
  sudo chmod +x /usr/local/bin/smartplaylists/orchestrator.py
  sudo mkdir -p /var/log/smartplaylists

Cron (ogni giorno alle 3:00):
  0 3 * * * /usr/bin/python3 /usr/local/bin/smartplaylists/orchestrator.py

Log:
  /var/log/smartplaylists/orchestrator.log
"""

import sys
import os
import logging
import subprocess
from datetime import datetime

# Assicura che Python trovi i moduli nella stessa directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    LOG_DIR, LOG_FILE,
    EXCLUDED_USERS,
    NOTIFY_EMAIL, NOTIFY_ON_ERROR_ONLY,
)
from lib_jellyfin import JellyfinClient

import playlist_top_tracks
import playlist_recent
import playlist_daily_mix
import playlist_top_period

# ── Setup logging ─────────────────────────────────────────────────────────────

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ── Definizione pipeline playlist ─────────────────────────────────────────────
# Aggiungi o rimuovi moduli qui per cambiare quali playlist vengono generate.

GENERATORS = [
    ("Top Brani",         playlist_top_tracks),
    ("Recenti",           playlist_recent),
    ("Daily Mix",         playlist_daily_mix),
    ("Top del Periodo",   playlist_top_period),
]


# ── Notifica mail ─────────────────────────────────────────────────────────────

def send_notification(subject: str, body: str):
    if not NOTIFY_EMAIL:
        return
    try:
        msg = f"To: {NOTIFY_EMAIL}\nSubject: {subject}\n\n{body}"
        subprocess.run(["msmtp", NOTIFY_EMAIL],
                       input=msg.encode(), check=True, timeout=30)
        log.info(f"Notifica inviata a {NOTIFY_EMAIL}")
    except Exception as e:
        log.error(f"Invio notifica fallito: {e}")


# ── Orchestratore ─────────────────────────────────────────────────────────────

def run():
    start = datetime.now()
    log.info("=" * 65)
    log.info("Smart Playlists Orchestrator — AVVIO")
    log.info(f"Data: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 65)

    jf = JellyfinClient()

    # 1. Recupera tutti gli utenti Jellyfin
    users = jf.get_all_users()
    if not users:
        log.error("Impossibile recuperare utenti da Jellyfin. Controllare URL e API Key.")
        send_notification(
            "[Jellyfin] Smart Playlists — ERRORE CRITICO",
            "Impossibile recuperare utenti da Jellyfin.\n"
            f"Controllare JELLYFIN_URL e JELLYFIN_API_KEY in config.py\n"
            f"Log: {LOG_FILE}",
        )
        sys.exit(1)

    # 2. Filtra utenti esclusi
    active_users = [u for u in users if u["name"] not in EXCLUDED_USERS]
    log.info(f"Utenti trovati: {len(users)} | Esclusi: {len(users) - len(active_users)} "
             f"| Da processare: {len(active_users)}")

    # 3. Per ogni utente, esegui tutti i generatori
    report = []          # riepilogo per eventuale mail
    total_errors = 0

    for user in active_users:
        uid   = user["id"]
        uname = user["name"]
        log.info("")
        log.info(f"── Utente: {uname} ({uid}) ──────────────────────────────")

        user_errors = 0

        for gen_name, gen_module in GENERATORS:
            log.info(f"  → {gen_name}")
            try:
                ok = gen_module.generate(
                    jellyfin_user_id=uid,
                    jellyfin_user_name=uname,
                )
                if not ok:
                    user_errors += 1
                    log.warning(f"  ✗ {gen_name} completato con errori per {uname}")
                else:
                    log.info(f"  ✓ {gen_name} OK")
            except Exception as e:
                user_errors += 1
                log.error(f"  ✗ {gen_name} eccezione per {uname}: {e}", exc_info=True)

        total_errors += user_errors
        status = "✓ OK" if user_errors == 0 else f"✗ {user_errors} errori"
        report.append(f"  {uname}: {status}")

    # 4. Riepilogo finale
    elapsed = (datetime.now() - start).total_seconds()
    log.info("")
    log.info("=" * 65)
    log.info(f"Completato in {elapsed:.1f}s | Errori totali: {total_errors}")
    log.info("Riepilogo per utente:")
    for line in report:
        log.info(line)
    log.info("=" * 65)

    # 5. Notifiche mail
    if total_errors > 0:
        send_notification(
            subject=f"[Jellyfin] Smart Playlists — {total_errors} ERRORI",
            body=(
                f"Il generatore ha completato con {total_errors} errori.\n\n"
                f"Riepilogo utenti:\n" + "\n".join(report) +
                f"\n\nDurata: {elapsed:.1f}s\nLog completo: {LOG_FILE}"
            ),
        )
    elif not NOTIFY_ON_ERROR_ONLY and NOTIFY_EMAIL:
        send_notification(
            subject="[Jellyfin] Smart Playlists — aggiornate",
            body=(
                f"Tutte le playlist aggiornate con successo.\n\n"
                f"Riepilogo utenti:\n" + "\n".join(report) +
                f"\n\nDurata: {elapsed:.1f}s\nLog: {LOG_FILE}"
            ),
        )

    return total_errors == 0


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)