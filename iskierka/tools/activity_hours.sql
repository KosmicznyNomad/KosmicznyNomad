-- ===========================================================================
-- get_whatsapp_activity_hours — zapytania na Collectorze
-- Tabela zrodlowa: "MessageRaw" (repo whatsapp-qr-data-collector, Prisma)
-- ===========================================================================
--
-- TRZY OSIE CZASU. Mylenie ich to cicha utrata danych:
--
--   messageTimestamp  NULLABLE  czas nadania (WhatsApp).      indeks: TAK
--   createdAt         NOT NULL  czas przyjecia przez Collector. indeks: TAK
--   updatedAt         NOT NULL  ostatnia mutacja wiersza.      indeks: NIE (!)
--
-- Ta sonda kubelkuje po OSI BIZNESOWEJ: COALESCE(messageTimestamp, createdAt).
-- get_whatsapp_updates jedzie po OSI PRZYJECIA (createdAt) i tak ma zostac —
-- dzieki temu obejmuje wiadomosci dosylane po reconnect, ktore maja stary
-- czas nadania, ale swiezy czas zapisu.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. INDEKSY
-- ---------------------------------------------------------------------------

-- Wymagany przez te sonde: bucketowanie po osi biznesowej z obsluga NULL.
CREATE INDEX CONCURRENTLY IF NOT EXISTS "MessageRaw_effective_ts_idx"
  ON "MessageRaw" ((COALESCE("messageTimestamp", "createdAt")));

-- NIEZALEZNA OD TEJ SONDY, ale warta naprawy: istniejacy filtr ?updatedAfter=
-- w apps/api (MessagesService.buildWhere) robi where.updatedAt >= ...,
-- a na updatedAt NIE MA indeksu. Na tabeli tej wielkosci to seq scan.
CREATE INDEX CONCURRENTLY IF NOT EXISTS "MessageRaw_updatedAt_idx"
  ON "MessageRaw" ("updatedAt");


-- ---------------------------------------------------------------------------
-- 2. HISTOGRAM GODZINOWY (bez tresci wiadomosci)
-- ---------------------------------------------------------------------------
-- Godziny lokalne Europe/Warsaw, swiadome DST.
--
-- Grupujemy po (etykieta, offset), NIE po samej etykiecie. W pazdzierniku
-- lokalna godzina 02:00 wystepuje dwa razy — raz z +02:00, raz z +01:00.
-- To dwie rozne, realne godziny; grupowanie po etykiecie scalilo by je w jedna.
-- W marcu 02:00 nie istnieje wcale i po prostu nie ma takiego wiersza.
--
-- :since, :until — timestamptz
SELECT
  to_char(
    date_trunc('hour', COALESCE("messageTimestamp", "createdAt") AT TIME ZONE 'Europe/Warsaw'),
    'YYYY-MM-DD"T"HH24:00'
  )                                                   AS bucket_local,
  to_char(COALESCE("messageTimestamp", "createdAt") AT TIME ZONE 'Europe/Warsaw', 'OF')
                                                      AS utc_offset,
  min(COALESCE("messageTimestamp", "createdAt"))      AS sort_key,
  count(*)                                            AS total,
  count(*) FILTER (WHERE "direction" = 'INCOMING')    AS incoming,
  count(*) FILTER (WHERE "direction" = 'OUTGOING')    AS outgoing,
  count(DISTINCT "chatId")                            AS conversations,
  count(*) FILTER (WHERE "hasMedia")                  AS with_media,
  -- jawnie raportowany dlug danych, nigdy ukrywany:
  count(*) FILTER (WHERE "messageTimestamp" IS NULL)  AS fallback_to_ingest
FROM "MessageRaw"
WHERE COALESCE("messageTimestamp", "createdAt") >= :since
  AND COALESCE("messageTimestamp", "createdAt") <  :until
GROUP BY bucket_local, utc_offset
ORDER BY sort_key;


-- ---------------------------------------------------------------------------
-- 3. DEDUPLIKACJA KOPII GRUPOWYCH
-- ---------------------------------------------------------------------------
-- @@unique([evolutionInstanceName, messageId]) jest PER INSTANCJA, wiec jedna
-- wiadomosc w grupie z pieciorgiem pracownikow to piec realnych wierszy.
-- Skala jest istotna: w jednym przebiegu get_whatsapp_updates zdjeto 32 kopie
-- ze 176 wierszy, a w wyszukiwaniu globalnym potrafi to byc kilkanascie tysiecy.
--
-- Liczymy histogram na wierszach JUZ zdeduplikowanych, inaczej godziny z ruchem
-- grupowym sa sztucznie zawyzone proporcjonalnie do liczby pracownikow w grupie.
WITH deduped AS (
  SELECT DISTINCT ON ("chatId", "messageId")
    "chatId",
    "messageId",
    "direction",
    "hasMedia",
    COALESCE("messageTimestamp", "createdAt") AS effective_ts,
    ("messageTimestamp" IS NULL)              AS used_ingest_fallback
  FROM "MessageRaw"
  WHERE COALESCE("messageTimestamp", "createdAt") >= :since
    AND COALESCE("messageTimestamp", "createdAt") <  :until
  ORDER BY "chatId", "messageId", "createdAt" ASC, "id" ASC
)
SELECT
  to_char(date_trunc('hour', effective_ts AT TIME ZONE 'Europe/Warsaw'),
          'YYYY-MM-DD"T"HH24:00')                  AS bucket_local,
  to_char(effective_ts AT TIME ZONE 'Europe/Warsaw', 'OF') AS utc_offset,
  min(effective_ts)                                AS sort_key,
  count(*)                                         AS total,
  count(*) FILTER (WHERE "direction" = 'INCOMING') AS incoming,
  count(*) FILTER (WHERE "direction" = 'OUTGOING') AS outgoing,
  count(DISTINCT "chatId")                         AS conversations,
  count(*) FILTER (WHERE "hasMedia")               AS with_media,
  count(*) FILTER (WHERE used_ingest_fallback)     AS fallback_to_ingest
FROM deduped
GROUP BY bucket_local, utc_offset
ORDER BY sort_key;
