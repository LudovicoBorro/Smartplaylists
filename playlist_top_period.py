"""
playlist_top_period.py — Preferiti del Periodo
================================================
Per ogni utente crea la playlist con i brani più ascoltati
in un periodo specifico (default: ultimo mese).

A differenza di Top Brani (storico totale), questa playlist
ruota ogni refresh e riflette i gusti attuali dell'utente.

La playlist è privata per utente.
"""

import logging
from config import TOP_PERIOD
from lib_jellyfin import JellyfinClient
from lib_jellystat import JellystatClient

log = logging.getLogger(__name__)


def generate(jellyfin_user_id: str, jellyfin_user_name: str) -> bool:
    """
    Genera la playlist Top del Periodo per un singolo utente.
    Ritorna True se completato senza errori.
    """
    cfg = TOP_PERIOD
    log.info(f"[top_period] Utente: {jellyfin_user_name}")

    jf = JellyfinClient()
    js = JellystatClient()

    # 1. Recupera play counts nel periodo da Jellystat
    play_counts = js.get_play_counts_in_period(
        jellyfin_user_id=jellyfin_user_id,
        days=cfg["days"],
    )

    if not play_counts:
        log.warning(f"[top_period] Nessun ascolto negli ultimi {cfg['days']} giorni "
                    f"per {jellyfin_user_name}, playlist saltata")
        return True

    # 2. Ordina per play count decrescente e prendi i top N
    sorted_items = sorted(play_counts.items(), key=lambda x: x[1], reverse=True)
    top_ids = [iid for iid, _ in sorted_items[:cfg["count"]]]

    # 3. Valida che i brani esistano ancora in libreria
    valid_ids = jf.validate_item_ids(jellyfin_user_id, top_ids)

    if not valid_ids:
        log.warning(f"[top_period] Nessun brano valido per {jellyfin_user_name}")
        return True

    log.info(f"[top_period] {len(valid_ids)} brani validi per {jellyfin_user_name} "
             f"(ultimi {cfg['days']} giorni)")

    # 4. Aggiorna la playlist (ordine: più ascoltato prima nel periodo)
    success = jf.update_playlist(
        user_id=jellyfin_user_id,
        name=cfg["playlist_name"],
        item_ids=valid_ids,
        randomize=False,
    )

    if success:
        log.info(f"[top_period] ✓ '{cfg['playlist_name']}' aggiornata "
                 f"({len(valid_ids)} brani) per {jellyfin_user_name}")
    else:
        log.error(f"[top_period] ✗ Errore aggiornamento playlist per {jellyfin_user_name}")

    return success