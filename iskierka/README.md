# Iskierka — sonda godzinowa

Dokładka do zestawu narzędzi MCP wystawianego do ChatGPT i Claude.

## Co już jest, a czego brakowało

Sprawdzone na działającej instancji 20.08.2026. Serwer wystawia sześć narzędzi.
Pobieranie przyrostowe **już istnieje** i działa poprawnie:

| Potrzeba | Narzędzie | Stan |
|---|---|---|
| Okno liczone w godzinach | `get_whatsapp_messages_by_time` z `last_hours` (1–168) | jest |
| Pobranie tylko nowych, bez duplikatów | `get_whatsapp_updates` z `after_cursor` | jest |
| **Rozkład ruchu po godzinach bez pobierania treści** | — | **brakowało** |

### Weryfikacja pętli przyrostowej

Pierwszy przebieg, `lookback_minutes=180`:

```
boundary_basis        collector_ingestion_order
raw_messages          176
duplicate_rows_removed 32
total_messages        117   (16 rozmów)
duration_ms           76
```

Drugi przebieg z `after_cursor` → `total_messages: 0`, `cursor_applied: true`,
a `next_cursor` **niezmieniony**. Pusty wynik nie przesuwa znacznika, więc
wiadomość dosłana po reconnect nie wpadnie w lukę.

Kursor to podpisany token `u1.<payload>.<hmac>`:

```json
{"v":1,"created_at":"2026-08-20T08:22:47.701Z","id":"9ceb3f0d-…","scope":"dg:in:*"}
```

Klucz złożony `(created_at, id)` — czyli keyset po osi przyjęcia przez Collector,
z rozstrzyganiem remisów po `id`. `scope` wiąże kursor z filtrami (`dg` = direct
+ grupy, `in` = tylko przychodzące), więc kontynuacja ze zmienionymi filtrami nie
przejdzie po cichu. Ta konstrukcja jest poprawna i nie wymaga zmian.

## Czego dokłada `get_whatsapp_activity_hours`

To realizacja tej części zapotrzebowania, która brzmiała „żeby nie pobierać
więcej niż trzeba, a jak trzeba to wczytywać".

Dziś, żeby dowiedzieć się, że między 07:49 a 10:22 spłynęło 117 wiadomości
w 16 rozmowach, trzeba **pobrać te 117 wiadomości** plus 45 referencji do zdjęć.
Sonda odpowiada na to samo pytanie licznikami, bez treści.

Wzorzec pracy:

```
get_whatsapp_activity_hours(last_hours=12)   → gdzie jest ruch
        ↓ wybór dwóch–trzech godzin
get_whatsapp_messages_by_time(start/end)     → tylko te godziny
```

## Pliki

- `tools/activity_hours.py` — opis narzędzia, schemat wejścia, logika okna,
  kubełkowania i deduplikacji
- `tools/activity_hours.sql` — zapytania i indeksy
- `tools/test_activity_hours.py` — 15 testów, `python3 test_activity_hours.py`

## Dwie pułapki, które kod obchodzi

**Zmiana czasu.** 25.10.2026 lokalna godzina 02:00 występuje dwa razy — raz
z offsetem `+02:00`, raz z `+01:00`. Kubełki są kluczowane parą
`(etykieta, offset)` i sortowane po realnym UTC, nie po etykiecie. Grupowanie po
samej etykiecie scaliłoby dwie różne godziny w jedną. 29.03.2026 godzina 02:00
nie istnieje wcale i po prostu nie ma takiego kubełka. Oba przypadki mają test.

**Puste `messageTimestamp`.** Kolumna jest nullable i w produkcji realnie bywa
pusta (wiersze `message_type='unknown'`). Zwykły filtr na tej kolumnie wyciąłby
takie wiadomości bez śladu, a liczniki przestałyby się zgadzać z pozostałymi
narzędziami. Kod schodzi wtedy na czas przyjęcia i raportuje to jawnie jako
`fallback_to_ingest`.

## Znaleziska poboczne w Collectorze

**Brak indeksu na `updatedAt`.** `MessagesService.buildWhere` obsługuje
`?updatedAfter=` przez `where.updatedAt >= …`, ale w `schema.prisma` indeksy są
na `messageTimestamp` i `createdAt` — na `updatedAt` nie ma żadnego. Na tabeli
tej wielkości to sekwencyjny skan. SQL w `activity_hours.sql` zawiera gotowy
`CREATE INDEX CONCURRENTLY`.

**Referencje rozmów nie są przenośne między narzędziami.** `conversation_ref`
zwrócony przez jedno narzędzie, podany do drugiego, potrafi trafić w inną
rozmowę i zwrócić pustą listę **bez błędu**. Bezpieczna ścieżka to `contact`
razem z zakresem dat.
