"""
Iskierka — narzędzie MCP: get_whatsapp_activity_hours

Tania sonda godzinowa. Zwraca WYŁĄCZNIE liczniki, bez treści wiadomości,
żeby model mógł zobaczyć, gdzie jest ruch, zanim cokolwiek pobierze.

Domyka lukę w istniejącym zestawie:

  get_whatsapp_messages_by_time   okno czasu -> pełna treść
  get_whatsapp_updates            kursor przyrostowy -> pełna treść
  get_whatsapp_today_activity     dziś, per rozmowa, BEZ podziału na godziny
  >>> get_whatsapp_activity_hours <<<  rozkład godzinowy, BEZ treści

Wzorzec użycia: sonda -> wybór godzin -> dociągnięcie tylko tych godzin
przez get_whatsapp_messages_by_time(start/end).

Konwencje zgodne z resztą serwera (zweryfikowane na działającej instancji):
  data_source = "collector", strefa Europe/Warsaw, blok period z boundary_basis,
  raportowanie deduplikacji jako raw/scoped/duplicate_rows_removed/total.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")

MAX_LAST_HOURS = 168
MAX_BUCKETS = 24 * 31


# ---------------------------------------------------------------------------
# Opis narzędzia — w konwencji pozostałych narzędzi Iskierki
# ---------------------------------------------------------------------------

DESCRIPTION = """\
Tania sonda rozkładu ruchu. Użyj ZAWSZE jako pierwszy krok, gdy pytanie obejmuje \
więcej niż kilka godzin albo brzmi „co się działo”, „kiedy było gorąco”, „ile tego \
jest”. Zwraca wyłącznie liczniki wiadomości w podziale na godziny lokalne \
Europe/Warsaw — bez treści, więc nie zajmuje kontekstu. Na podstawie zwróconego \
rozkładu wybierz konkretne godziny i dopiero po nie sięgnij przez \
get_whatsapp_messages_by_time ze start_date i end_date albo przez \
get_whatsapp_updates. Nie pobieraj całego dnia, jeżeli ruch był w trzech godzinach. \
Każdy kubełek niesie offset UTC, ponieważ przy zmianie czasu godzina lokalna bywa \
niejednoznaczna. Pole fallback_to_ingest podaje, ile wiadomości nie miało własnego \
czasu nadania i zostało zakwalifikowanych po czasie przyjęcia przez Collector — \
nie pomijaj go, gdy liczby mają się zgadzać z innymi narzędziami.\
"""

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "last_hours": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_LAST_HOURS,
            "description": (
                "Liczba ostatnich pełnych godzin liczonych od teraz wstecz, 1–168. "
                "Wyklucza się ze start_date/end_date. Gdy nie podano żadnego zakresu, "
                "serwer przyjmie 24 godziny."
            ),
        },
        "start_date": {
            "type": "string",
            "pattern": r"^\d{4}-\d{2}-\d{2}$",
            "description": "Początek jawnego zakresu, lokalnie, włącznie. Podaj razem z end_date.",
        },
        "end_date": {
            "type": "string",
            "pattern": r"^\d{4}-\d{2}-\d{2}$",
            "description": "Koniec jawnego zakresu, lokalnie, włącznie.",
        },
        "employee_name": {
            "type": "string",
            "minLength": 2,
            "description": (
                "Właściciel konta WhatsApp. Pomiń, aby objąć wszystkie aktywne konta. "
                "Nie zgaduj osoby, gdy pytanie jej nie wskazuje."
            ),
        },
        "granularity": {
            "type": "string",
            "enum": ["hour", "day"],
            "default": "hour",
            "description": "Rozmiar kubełka. Użyj day dla zakresów dłuższych niż tydzień.",
        },
        "include_direct": {"type": "boolean", "default": True},
        "include_groups": {"type": "boolean", "default": True},
        "only_incoming": {
            "type": "boolean",
            "default": False,
            "description": "Ustaw true dla pytań typu „co do nas spłynęło”.",
        },
        "top_conversations": {
            "type": "integer",
            "minimum": 0,
            "maximum": 10,
            "default": 3,
            "description": (
                "Ile najaktywniejszych rozmów wymienić przy każdym kubełku. "
                "Ustaw 0, aby zwrócić same liczniki."
            ),
        },
    },
    "additionalProperties": False,
}

ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


# ---------------------------------------------------------------------------
# Rozwiązywanie okna czasu
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Window:
    start: datetime          # aware, UTC
    end: datetime            # aware, UTC
    mode: str                # "last_hours" | "explicit_range" | "default"
    granularity: str


class InvalidWindowError(ValueError):
    """Błąd wejścia z podpowiedzią naprawy — komunikat trafia wprost do modelu."""


def resolve_window(
    *,
    now: datetime,
    last_hours: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    granularity: str = "hour",
) -> Window:
    """
    Zamienia wejście na domknięte okno UTC.

    Reguły:
      - last_hours i start_date/end_date wykluczają się wzajemnie,
      - jawny zakres jest WŁĄCZNY po obu stronach, więc end_date rozciąga się
        do końca tego dnia lokalnie,
      - brak zakresu = ostatnie 24 godziny.
    """
    if granularity not in ("hour", "day"):
        raise InvalidWindowError(
            f"Nieznana granulacja {granularity!r}. Użyj 'hour' albo 'day'."
        )

    has_range = bool(start_date or end_date)

    if last_hours is not None and has_range:
        raise InvalidWindowError(
            "Podano jednocześnie last_hours i zakres dat. "
            "Wybierz jedno: last_hours dla okresu liczonego od teraz wstecz, "
            "albo start_date razem z end_date dla przedziału od–do."
        )

    if has_range:
        if not (start_date and end_date):
            raise InvalidWindowError(
                "Jawny zakres wymaga obu dat. Podaj start_date i end_date "
                "w formacie YYYY-MM-DD."
            )
        try:
            start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_d = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise InvalidWindowError(
                f"Nieprawidłowa data: {exc}. Oczekiwany format to YYYY-MM-DD."
            ) from exc

        if end_d < start_d:
            raise InvalidWindowError(
                f"end_date ({end_date}) jest wcześniejszy niż start_date ({start_date}). "
                "Zamień daty miejscami."
            )

        start_local = datetime.combine(start_d, datetime.min.time(), tzinfo=TZ)
        # end_date włącznie -> północ dnia następnego
        end_local = datetime.combine(end_d, datetime.min.time(), tzinfo=TZ) + timedelta(days=1)
        window = Window(
            start=start_local.astimezone(timezone.utc),
            end=end_local.astimezone(timezone.utc),
            mode="explicit_range",
            granularity=granularity,
        )
    elif last_hours is not None:
        if not 1 <= last_hours <= MAX_LAST_HOURS:
            raise InvalidWindowError(
                f"last_hours={last_hours} poza zakresem. Dozwolone 1–{MAX_LAST_HOURS}. "
                "Dla dłuższych okresów użyj start_date i end_date z granularity='day'."
            )
        end_utc = now.astimezone(timezone.utc)
        window = Window(
            start=end_utc - timedelta(hours=last_hours),
            end=end_utc,
            mode="last_hours",
            granularity=granularity,
        )
    else:
        end_utc = now.astimezone(timezone.utc)
        window = Window(
            start=end_utc - timedelta(hours=24),
            end=end_utc,
            mode="default",
            granularity=granularity,
        )

    _guard_bucket_count(window)
    return window


def _guard_bucket_count(window: Window) -> None:
    span_hours = (window.end - window.start).total_seconds() / 3600
    buckets = span_hours if window.granularity == "hour" else span_hours / 24
    if buckets > MAX_BUCKETS:
        raise InvalidWindowError(
            f"Zakres daje {int(buckets)} kubełków, limit to {MAX_BUCKETS}. "
            "Zawęź okres albo ustaw granularity='day'."
        )


# ---------------------------------------------------------------------------
# Bucketowanie
# ---------------------------------------------------------------------------


@dataclass
class Bucket:
    label: str
    utc_offset: str
    sort_key: datetime           # początek kubełka w UTC — jedyna pewna oś porządku
    total: int = 0
    incoming: int = 0
    outgoing: int = 0
    with_media: int = 0
    fallback_to_ingest: int = 0
    conversations: set[str] = field(default_factory=set)

    def as_dict(self, top: list[tuple[str, int]]) -> dict[str, Any]:
        out: dict[str, Any] = {
            "bucket_local": self.label,
            "utc_offset": self.utc_offset,
            "total": self.total,
            "incoming": self.incoming,
            "outgoing": self.outgoing,
            "conversations": len(self.conversations),
            "with_media": self.with_media,
        }
        if self.fallback_to_ingest:
            out["fallback_to_ingest"] = self.fallback_to_ingest
        if top:
            out["top_conversations"] = [
                {"display_name": name, "messages": count} for name, count in top
            ]
        return out


def bucket_key(ts_utc: datetime, granularity: str) -> tuple[str, str, datetime]:
    """
    Zwraca (etykieta lokalna, offset UTC, początek kubełka w UTC).

    Offset NIE jest ozdobnikiem — jest częścią klucza. Przy zmianie czasu
    w październiku godzina lokalna 02:00 występuje dwa razy, raz z offsetem
    +02:00 i raz z +01:00. To dwie różne, realne godziny. Kluczowanie samą
    etykietą scaliłoby je w jeden kubełek i zgubiło rozróżnienie.
    W marcu 02:00 nie istnieje wcale i po prostu nie ma takiego kubełka.
    """
    local = ts_utc.astimezone(TZ)
    if granularity == "day":
        label = local.strftime("%Y-%m-%d")
        truncated = local.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        label = local.strftime("%Y-%m-%dT%H:00")
        truncated = local.replace(minute=0, second=0, microsecond=0)
    offset = local.strftime("%z")
    return label, f"{offset[:3]}:{offset[3:]}", truncated.astimezone(timezone.utc)


def build_histogram(
    rows: list[dict[str, Any]],
    *,
    granularity: str = "hour",
    top_conversations: int = 3,
) -> dict[str, Any]:
    """
    rows: wiersze z Collectora. Wymagane klucze:
        message_timestamp (datetime|None), created_at (datetime),
        direction ("INCOMING"|"OUTGOING"|"UNKNOWN"),
        chat_id (str), display_name (str), has_media (bool)

    Kubełkujemy po czasie NADANIA, a gdy go brak — po czasie PRZYJĘCIA.
    messageTimestamp jest nullable i w produkcji realnie bywa pusty; zwykły
    filtr na tej kolumnie wyciąłby takie wiersze bez śladu. Liczbę podmian
    raportujemy jawnie jako fallback_to_ingest.
    """
    buckets: dict[tuple[str, str], Bucket] = {}
    per_bucket_convo: dict[tuple[str, str], dict[str, int]] = {}
    fallback_total = 0

    for row in rows:
        ts = row.get("message_timestamp")
        used_fallback = ts is None
        if used_fallback:
            ts = row["created_at"]
            fallback_total += 1

        label, offset, sort_key = bucket_key(ts, granularity)
        key = (label, offset)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = Bucket(label=label, utc_offset=offset, sort_key=sort_key)
            buckets[key] = bucket
            per_bucket_convo[key] = {}

        bucket.total += 1
        direction = row.get("direction")
        if direction == "INCOMING":
            bucket.incoming += 1
        elif direction == "OUTGOING":
            bucket.outgoing += 1
        if row.get("has_media"):
            bucket.with_media += 1
        if used_fallback:
            bucket.fallback_to_ingest += 1

        bucket.conversations.add(row["chat_id"])
        name = row.get("display_name") or row["chat_id"]
        convo = per_bucket_convo[key]
        convo[name] = convo.get(name, 0) + 1

    # Porządek po realnym czasie UTC, nie po etykiecie — inaczej przy zmianie
    # czasu dwie godziny 02:00 ustawiłyby się w dowolnej kolejności.
    ordered = sorted(buckets.items(), key=lambda kv: kv[1].sort_key)

    out_buckets = []
    for key, bucket in ordered:
        top: list[tuple[str, int]] = []
        if top_conversations > 0:
            top = sorted(
                per_bucket_convo[key].items(),
                key=lambda kv: (-kv[1], kv[0]),
            )[:top_conversations]
        out_buckets.append(bucket.as_dict(top))

    total = sum(b.total for _, b in ordered)
    busiest = sorted(
        (b for _, b in ordered), key=lambda b: (-b.total, b.sort_key)
    )[:3]

    return {
        "buckets": out_buckets,
        "total_messages": total,
        "bucket_count": len(ordered),
        "busiest": [
            {"bucket_local": b.label, "utc_offset": b.utc_offset, "total": b.total}
            for b in busiest
            if b.total
        ],
        "fallback_to_ingest_total": fallback_total,
    }


def deduplicate_group_copies(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """
    Jedna wiadomość z grupy, w której siedzi pięciu pracowników, to pięć realnych
    wierszy — @@unique([evolutionInstanceName, messageId]) jest per instancja.
    Zostawiamy najwcześniej zapisaną kopię każdej pary (chat_id, message_id).

    Zwraca (wiersze, liczba usuniętych).
    """
    best: dict[tuple[str, str], dict[str, Any]] = {}
    removed = 0
    for row in rows:
        key = (row["chat_id"], row["message_id"])
        current = best.get(key)
        if current is None:
            best[key] = row
        else:
            removed += 1
            if row["created_at"] < current["created_at"]:
                best[key] = row
    return list(best.values()), removed


def build_response(
    rows: list[dict[str, Any]],
    *,
    window: Window,
    scope: str,
    searched_employees: list[str],
    only_incoming: bool,
    top_conversations: int = 3,
) -> dict[str, Any]:
    """Składa odpowiedź w konwencji pozostałych narzędzi Iskierki."""
    raw_count = len(rows)
    deduped, removed = deduplicate_group_copies(rows)
    histogram = build_histogram(
        deduped, granularity=window.granularity, top_conversations=top_conversations
    )

    start_local = window.start.astimezone(TZ)
    end_local = window.end.astimezone(TZ)

    return {
        "data_source": "collector",
        "scope": scope,
        "period": {
            "start_local_time": start_local.strftime("%Y-%m-%d %H:%M"),
            "end_local_time": end_local.strftime("%Y-%m-%d %H:%M"),
            "time_zone": "Europe/Warsaw",
            "boundary_basis": "whatsapp_send_time_with_ingest_fallback",
            "mode": window.mode,
            "granularity": window.granularity,
        },
        "searched_employees": searched_employees,
        "only_incoming": only_incoming,
        "raw_messages": raw_count,
        "duplicate_rows_removed": removed,
        "total_messages": histogram["total_messages"],
        "bucket_count": histogram["bucket_count"],
        "buckets": histogram["buckets"],
        "busiest": histogram["busiest"],
        "fallback_to_ingest_total": histogram["fallback_to_ingest_total"],
        "next_step": (
            "Wybierz godziny z największym ruchem i pobierz wyłącznie je przez "
            "get_whatsapp_messages_by_time ze start_date i end_date, albo kontynuuj "
            "pętlę przez get_whatsapp_updates."
        ),
    }
