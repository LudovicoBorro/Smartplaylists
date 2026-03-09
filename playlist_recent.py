"""
playlist_recent.py — Ascoltati di Recente
==========================================
Per ogni utente crea/aggiorna la playlist con i brani
ascoltati negli ultimi N giorni, ordinati dal più recente.

La playlist è privata per utente.
"""

import logging
from config import RECENT
from lib_jellyfin import JellyfinClient
from lib_jellystat import JellystatClient

log = logging.getLogger(__name__)


def generate(jellyfin_user_id: str, jellyfin_user_name: str) -> bool:
    """
    Genera la playlist Ascoltati di Recente per un singolo utente.
    Ritorna True se completato senza errori.
    """
    cfg = RECENT
    log.info(f"[recent] Utente: {jellyfin_user_name}")

    jf = JellyfinClient()
    js = JellystatClient()

    # 1. Recupera brani recenti da Jellystat
    recent = js.get_recent_tracks(
        jellyfin_user_id=jellyfin_user_id,
        days=cfg["days"],
        limit=cfg["count"],
    )

    if not recent:
        log.warning(f"[recent] Nessun ascolto negli ultimi {cfg['days']} giorni "
                    f"per {jellyfin_user_name}, playlist saltata")
        return True

    # 2. Estrai ID e valida
    raw_ids = [t["itemId"] for t in recent if t.get("itemId")]
    valid_ids = jf.validate_item_ids(jellyfin_user_id, raw_ids)

    if not valid_ids:
        log.warning(f"[recent] Nessun brano valido per {jellyfin_user_name}")
        return True

    log.info(f"[recent] {len(valid_ids)} brani validi per {jellyfin_user_name}")

    # 3. Aggiorna playlist (ordine: più recente prima)
    success = jf.update_playlist(
        user_id=jellyfin_user_id,
        name=cfg["playlist_name"],
        item_ids=valid_ids,
        randomize=False,
    )

    if success:
        log.info(f"[recent] ✓ '{cfg['playlist_name']}' aggiornata "
                 f"({len(valid_ids)} brani) per {jellyfin_user_name}")
    else:
        log.error(f"[recent] ✗ Errore aggiornamento playlist per {jellyfin_user_name}")

    return success