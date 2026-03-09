"""
playlist_daily_mix.py — Daily Mix
===================================
Per ogni utente crea un mix bilanciato basato sui generi
che ascolta di più, con un boost per i brani recenti.

Logica:
  1. Analizza lo storico Jellystat dell'utente (ultimi N giorni)
  2. Mappa i brani ascoltati -> generi (via API Jellyfin)
  3. Se ci sono generi: seleziona brani da quei generi con boost recenti
  4. Fallback se mancano tag genere: mix casuale dai brani ascoltati
     di recente + brani non ancora ascoltati dalla libreria

La playlist e privata per utente.
"""

import logging
import random
from collections import Counter
from config import DAILY_MIX
from lib_jellyfin import JellyfinClient
from lib_jellystat import JellystatClient

log = logging.getLogger(__name__)


def generate(jellyfin_user_id: str, jellyfin_user_name: str) -> bool:
    cfg = DAILY_MIX
    log.info(f"[daily_mix] Utente: {jellyfin_user_name}")

    jf = JellyfinClient()
    js = JellystatClient()

    # 1. Recupera play counts per periodo di analisi
    play_counts = js.get_play_counts_in_period(
        jellyfin_user_id=jellyfin_user_id,
        days=cfg["analysis_days"],
    )
    if not play_counts:
        log.warning(f"[daily_mix] Nessun dato per {jellyfin_user_name}, saltato")
        return True

    # 2. Recupera brani recenti per il boost
    recent_data = js.get_recent_tracks(
        jellyfin_user_id=jellyfin_user_id,
        days=cfg["recent_boost_days"],
        limit=500,
    )
    recently_played_ids = {t["itemId"] for t in recent_data if t.get("itemId")}

    # 3. Risolvi generi per i brani ascoltati
    played_item_ids = list(play_counts.keys())
    genre_map = jf.get_genres_for_items(jellyfin_user_id, played_item_ids)

    # Conta generi pesati per play count
    genre_counter: Counter = Counter()
    items_with_genres = 0
    for iid, genres in genre_map.items():
        if genres:
            items_with_genres += 1
            plays = play_counts.get(iid, 1)
            for genre in genres:
                genre_counter[genre] += plays

    log.info(f"[daily_mix] {items_with_genres}/{len(played_item_ids)} brani "
             f"hanno tag genere per {jellyfin_user_name}")

    # ── Percorso A: ci sono tag genere ───────────────────────────────────────
    if genre_counter:
        top_genres = [g for g, _ in genre_counter.most_common(cfg["top_genres"])]
        log.info(f"[daily_mix] Generi top: {top_genres}")

        tracks_per_genre = max(1, cfg["count"] // len(top_genres))
        seen = set()
        final_ids = []

        for genre in top_genres:
            candidates = jf.get_audio_items_by_genre(
                user_id=jellyfin_user_id,
                genre=genre,
                limit=tracks_per_genre * 6,
            )
            if not candidates:
                log.warning(f"[daily_mix] Nessun brano per genere '{genre}'")
                continue

            boosted   = [it for it in candidates if it.get("Id") in recently_played_ids]
            unboosted = [it for it in candidates if it.get("Id") not in recently_played_ids]
            random.shuffle(boosted)
            random.shuffle(unboosted)
            # Boost = i recenti appaiono piu volte nel pool
            pool = (boosted * cfg["recent_boost_weight"]) + unboosted

            added = 0
            for item in pool:
                iid = item.get("Id")
                if iid and iid not in seen and added < tracks_per_genre:
                    final_ids.append(iid)
                    seen.add(iid)
                    added += 1

    # ── Percorso B: nessun tag genere — fallback su mix storico + casuali ────
    else:
        log.info(f"[daily_mix] Nessun tag genere trovato — "
                 f"uso fallback (recenti + brani non ascoltati)")

        # Prima meta: brani recenti (gia ascoltati, ordinati per recency)
        recent_ids = [t["itemId"] for t in recent_data if t.get("itemId")]
        half = cfg["count"] // 2
        final_ids = recent_ids[:half]
        seen = set(final_ids)

        # Seconda meta: brani casuali dalla libreria (inclusi non ascoltati)
        all_audio = jf.get_all_audio_items(
            user_id=jellyfin_user_id,
            limit=cfg["count"] * 4,
        )
        random.shuffle(all_audio)
        for item in all_audio:
            iid = item.get("Id")
            if iid and iid not in seen and len(final_ids) < cfg["count"]:
                final_ids.append(iid)
                seen.add(iid)

        random.shuffle(final_ids)

    if not final_ids:
        log.warning(f"[daily_mix] Nessun brano selezionato per {jellyfin_user_name}")
        return True

    # 4. Valida e aggiorna
    valid_ids = jf.validate_item_ids(jellyfin_user_id, final_ids)
    if not valid_ids:
        log.warning(f"[daily_mix] Nessun brano valido per {jellyfin_user_name}")
        return True

    random.shuffle(valid_ids)
    final = valid_ids[:cfg["count"]]

    success = jf.update_playlist(
        user_id=jellyfin_user_id,
        name=cfg["playlist_name"],
        item_ids=final,
        randomize=False,
    )

    if success:
        log.info(f"[daily_mix] '{cfg['playlist_name']}' aggiornata "
                 f"({len(final)} brani) per {jellyfin_user_name}")
    else:
        log.error(f"[daily_mix] Errore aggiornamento per {jellyfin_user_name}")

    return success