"""Testy sondy godzinowej. Uruchom: python3 -m pytest -q  albo  python3 test_activity_hours.py"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from activity_hours import (
    InvalidWindowError,
    build_histogram,
    build_response,
    bucket_key,
    deduplicate_group_copies,
    resolve_window,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 20, 10, 22, tzinfo=UTC)


def row(
    *,
    chat_id="chat-a",
    message_id=None,
    ts=None,
    created=None,
    direction="INCOMING",
    display_name="Kari",
    has_media=False,
):
    created = created or datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
    return {
        "chat_id": chat_id,
        "message_id": message_id or f"m-{chat_id}-{created.isoformat()}",
        "message_timestamp": ts,
        "created_at": created,
        "direction": direction,
        "display_name": display_name,
        "has_media": has_media,
    }


# --------------------------------------------------------------------------
# Okno czasu
# --------------------------------------------------------------------------


def test_last_hours_i_zakres_wykluczaja_sie():
    try:
        resolve_window(now=NOW, last_hours=2, start_date="2026-08-01", end_date="2026-08-02")
    except InvalidWindowError as exc:
        assert "Wybierz jedno" in str(exc)
    else:
        raise AssertionError("oczekiwano InvalidWindowError")


def test_zakres_wymaga_obu_dat():
    try:
        resolve_window(now=NOW, start_date="2026-08-01")
    except InvalidWindowError as exc:
        assert "obu dat" in str(exc)
    else:
        raise AssertionError("oczekiwano InvalidWindowError")


def test_end_date_jest_wlaczny():
    # 1–1 sierpnia to pełna doba, nie zero godzin.
    w = resolve_window(now=NOW, start_date="2026-08-01", end_date="2026-08-01")
    assert (w.end - w.start) == timedelta(days=1), w
    assert w.mode == "explicit_range"


def test_odwrocony_zakres_odrzucony():
    try:
        resolve_window(now=NOW, start_date="2026-08-05", end_date="2026-08-01")
    except InvalidWindowError as exc:
        assert "wcześniejszy" in str(exc)
    else:
        raise AssertionError("oczekiwano InvalidWindowError")


def test_last_hours_poza_zakresem():
    try:
        resolve_window(now=NOW, last_hours=500)
    except InvalidWindowError as exc:
        assert "1–168" in str(exc)
    else:
        raise AssertionError("oczekiwano InvalidWindowError")


def test_brak_zakresu_daje_24h():
    w = resolve_window(now=NOW)
    assert (w.end - w.start) == timedelta(hours=24)
    assert w.mode == "default"


def test_dlugi_zakres_godzinowy_odrzucony_z_podpowiedzia():
    try:
        resolve_window(
            now=NOW, start_date="2020-01-01", end_date="2026-01-01", granularity="hour"
        )
    except InvalidWindowError as exc:
        assert "granularity='day'" in str(exc)
    else:
        raise AssertionError("oczekiwano InvalidWindowError")


# --------------------------------------------------------------------------
# Zmiana czasu — najważniejszy test w tym pliku
# --------------------------------------------------------------------------


def test_pazdziernikowa_zmiana_czasu_nie_scala_dwoch_godzin_0200():
    """
    25.10.2026 o 03:00 CEST zegar cofa się na 02:00 CET.
    Lokalna 02:30 wypada wtedy DWA RAZY: raz z offsetem +02:00, raz z +01:00.
    To dwie różne godziny i muszą zostać dwoma kubełkami.
    """
    pierwsza = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)   # 02:30 +02:00
    druga = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)      # 02:30 +01:00

    l1, off1, _ = bucket_key(pierwsza, "hour")
    l2, off2, _ = bucket_key(druga, "hour")

    assert l1 == l2 == "2026-10-25T02:00", (l1, l2)
    assert off1 == "+02:00" and off2 == "+01:00", (off1, off2)

    hist = build_histogram(
        [row(ts=pierwsza, chat_id="a"), row(ts=druga, chat_id="b")],
        top_conversations=0,
    )
    assert hist["bucket_count"] == 2, hist["buckets"]
    # kolejność chronologiczna: najpierw +02:00, potem +01:00
    assert [b["utc_offset"] for b in hist["buckets"]] == ["+02:00", "+01:00"]
    assert hist["total_messages"] == 2


def test_marcowa_zmiana_czasu_przeskakuje_0200():
    """29.03.2026 o 02:00 zegar skacze na 03:00 — kubełka 02:00 po prostu nie ma."""
    tuz_przed = datetime(2026, 3, 29, 0, 30, tzinfo=UTC)  # 01:30 +01:00
    tuz_po = datetime(2026, 3, 29, 1, 30, tzinfo=UTC)     # 03:30 +02:00

    l1, off1, _ = bucket_key(tuz_przed, "hour")
    l2, off2, _ = bucket_key(tuz_po, "hour")

    assert l1 == "2026-03-29T01:00" and off1 == "+01:00"
    assert l2 == "2026-03-29T03:00" and off2 == "+02:00"


# --------------------------------------------------------------------------
# Puste messageTimestamp
# --------------------------------------------------------------------------


def test_null_timestamp_wpada_do_kubelka_po_czasie_przyjecia_i_jest_raportowany():
    """
    messageTimestamp jest nullable i w produkcji bywa NULL (zaobserwowane wiersze
    message_type='unknown'). Taki wiersz nie może zniknąć po cichu.
    """
    hist = build_histogram(
        [
            row(ts=datetime(2026, 8, 20, 7, 10, tzinfo=UTC)),
            row(ts=None, created=datetime(2026, 8, 20, 7, 40, tzinfo=UTC)),
        ],
        top_conversations=0,
    )
    assert hist["total_messages"] == 2
    assert hist["fallback_to_ingest_total"] == 1
    assert hist["bucket_count"] == 1
    assert hist["buckets"][0]["fallback_to_ingest"] == 1


def test_brak_fallbacku_nie_zasmieca_wyniku():
    hist = build_histogram(
        [row(ts=datetime(2026, 8, 20, 7, 10, tzinfo=UTC))], top_conversations=0
    )
    assert "fallback_to_ingest" not in hist["buckets"][0]


# --------------------------------------------------------------------------
# Deduplikacja kopii grupowych
# --------------------------------------------------------------------------


def test_kopie_grupowe_scalane_do_najwczesniejszej():
    wspolna = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
    rows = [
        row(chat_id="grupa", message_id="X", created=wspolna + timedelta(seconds=5)),
        row(chat_id="grupa", message_id="X", created=wspolna),
        row(chat_id="grupa", message_id="X", created=wspolna + timedelta(seconds=9)),
        row(chat_id="grupa", message_id="Y", created=wspolna),
    ]
    deduped, removed = deduplicate_group_copies(rows)
    assert removed == 2
    assert len(deduped) == 2
    zachowana = [r for r in deduped if r["message_id"] == "X"][0]
    assert zachowana["created_at"] == wspolna


def test_rozne_rozmowy_nie_sa_scalane():
    wspolna = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
    rows = [
        row(chat_id="a", message_id="X", created=wspolna),
        row(chat_id="b", message_id="X", created=wspolna),
    ]
    deduped, removed = deduplicate_group_copies(rows)
    assert removed == 0 and len(deduped) == 2


# --------------------------------------------------------------------------
# Odpowiedź jako całość
# --------------------------------------------------------------------------


def test_odpowiedz_liczy_ruch_i_wskazuje_najgoretsze_godziny():
    rows = []
    for i in range(3):
        rows.append(
            row(ts=datetime(2026, 8, 20, 6, 5, tzinfo=UTC), chat_id="a", message_id=f"a{i}")
        )
    for i in range(7):
        rows.append(
            row(
                ts=datetime(2026, 8, 20, 7, 5, tzinfo=UTC),
                chat_id="b",
                message_id=f"b{i}",
                display_name="Jacek Welicki",
            )
        )
    rows.append(
        row(
            ts=datetime(2026, 8, 20, 7, 30, tzinfo=UTC),
            chat_id="c",
            direction="OUTGOING",
            display_name="Patrycja",
            has_media=True,
        )
    )

    window = resolve_window(now=NOW, last_hours=6)
    resp = build_response(
        rows,
        window=window,
        scope="all_active_accounts",
        searched_employees=["Kamil Bukato"],
        only_incoming=False,
        top_conversations=2,
    )

    assert resp["data_source"] == "collector"
    assert resp["period"]["time_zone"] == "Europe/Warsaw"
    assert resp["period"]["boundary_basis"] == "whatsapp_send_time_with_ingest_fallback"
    # 3 kopie w rozmowie "a" mają różne message_id, więc nic nie znika
    assert resp["total_messages"] == 11
    assert resp["bucket_count"] == 2

    najgoretszy = resp["busiest"][0]
    assert najgoretszy["bucket_local"] == "2026-08-20T09:00", resp["busiest"]
    assert najgoretszy["total"] == 8

    drugi = resp["buckets"][1]
    assert drugi["incoming"] == 7 and drugi["outgoing"] == 1
    assert drugi["with_media"] == 1
    assert drugi["conversations"] == 2
    assert drugi["top_conversations"][0] == {"display_name": "Jacek Welicki", "messages": 7}


def test_top_conversations_zero_pomija_liste():
    window = resolve_window(now=NOW, last_hours=2)
    resp = build_response(
        [row(ts=datetime(2026, 8, 20, 9, 5, tzinfo=UTC))],
        window=window,
        scope="all_active_accounts",
        searched_employees=["Kamil Bukato"],
        only_incoming=True,
        top_conversations=0,
    )
    assert "top_conversations" not in resp["buckets"][0]


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok   {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} przeszło")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
