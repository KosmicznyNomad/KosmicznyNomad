---
name: nowy-artykul
description: Wciąga nowy artykuł do bazy wiedzy w baza/ i mapuje go według stałego procesu — pełny tekst do baza/artykuly/, wiersz w baza/INDEKS.md, notatka w baza/mapowania/ z tezą, ustaleniami, liczbami i materiałem do wykorzystania, na koniec commit. Używaj ZAWSZE, gdy użytkownik podaje link do artykułu, newslettera albo wpisu i mówi „wciągnij", „dodaj do bazy", „zmapuj", „przerób", „uruchom proces", „nowy artykuł" — a także gdy wkleja surowy tekst artykułu z prośbą o obróbkę, gdy prosi o pobranie tekstu z Substacka lub innego płatnego newslettera, gdy pyta „co już mam w bazie na temat X" albo prosi o aktualizację indeksu czy poprawienie istniejącego mapowania.
---

# Nowy artykuł

Proces od surowego źródła do notatki, z której da się korzystać za pół roku. Każdy krok zostawia ślad w repozytorium, więc baza rośnie sama z siebie, a nie w czyjejś głowie.

Sens całości: artykuł przeczytany i zamknięty jest stracony. Artykuł rozłożony na tezę, ustalenia i liczby zostaje jako materiał, po który można sięgnąć przy pisaniu, rozmowie z klientem albo decyzji technicznej.

## Układ bazy

```
baza/
├── PROCES.md              opis tego procesu
├── INDEKS.md              tabela wszystkich wpisów
├── artykuly/              pełne teksty, RRRR-MM-DD-slug.md
└── mapowania/             notatki, ta sama nazwa pliku co tekst
```

Jeśli katalogu nie ma, załóż go razem z pierwszym wpisem.

## 1. Pozyskanie tekstu

Celem jest pełny tekst, nie streszczenie i nie zajawka. Kolejność prób:

Gdy użytkownik wkleił tekst — bierz go wprost. Gdy podał link — pobierz stronę i wyciągnij treść. Gdy tekst jest za płatną ścianą, zanim powiesz, że się nie da, sprawdź kod strony: wiele newsletterów na Substacku wysyła pełną treść w HTML dla wyszukiwarek, nawet gdy przeglądarka pokazuje tylko wstęp. Szukaj bloku `available-content` i zobacz, czy kończy się w połowie zdania, czy na sekcji domykającej artykuł.

Dla Substacka archiwum pomaga znaleźć właściwy adres, gdy znasz tylko tytuł:
```
curl -s "https://<nazwa>.substack.com/api/v1/archive?sort=new&search=<tytuł>&limit=10"
```
Zwraca `canonical_url` i `audience`. Dla własnej domeny newslettera podstaw ją zamiast `<nazwa>.substack.com`.

Do wyciągnięcia treści użyj `scripts/wyciagnij.py` — zamienia stronę Substacka na czysty markdown z nagłówkami i linkami do wykresów. Dla innych źródeł napisz analogiczną ekstrakcję, ale zachowaj ten sam kształt wyniku.

Plik zapisz jako `baza/artykuly/RRRR-MM-DD-slug.md`, gdzie data to data publikacji, nie dzisiejsza. Na górze tytuł, podtytuł, autor, źródło, data i link do oryginału.

Zanim pójdziesz dalej, sprawdź ostatnie akapity. Tekst urwany w pół zdania oznacza, że masz tylko zajawkę — powiedz to wprost zamiast mapować kawałek.

## 2. Wpis do indeksu

Dopisz wiersz do tabeli w `baza/INDEKS.md`, najnowsze na górze:

| Data | Tytuł | Źródło | Autor | Status | Mapowanie |

Status na tym etapie to `pobrany`. Tytuł linkuje do pliku z tekstem.

## 3. Mapowanie

To jest właściwa robota. Przeczytaj cały tekst, nie tylko nagłówki, i napisz `baza/mapowania/RRRR-MM-DD-slug.md` według stałego układu. Stałość układu ma znaczenie: po dziesięciu wpisach da się przeskakiwać między notatkami i od razu wiedzieć, gdzie czego szukać.

**Teza** — jedno zdanie, o co autorowi naprawdę chodzi. Nie temat, tylko twierdzenie.

**Struktura** — prozą, nie listą, które sekcje o czym. Ma pozwolić wrócić do właściwego fragmentu bez czytania całości.

**Kluczowe ustalenia** — twierdzenia, które da się zacytować albo sprawdzić. Każde jako osobny akapit z wyjaśnieniem, dlaczego tak jest. To nie jest streszczenie akapit po akapicie — wybieraj to, co ma wagę.

**Liczby i dane** — konkretne wartości z tekstu. Liczby są tym, po co wraca się do notatki najczęściej, i tym, co najłatwiej przekręcić z pamięci.

**Co z tego dla mnie** — związek z projektami i tematami użytkownika. Jeśli nie ma związku, napisz to szczerze zamiast produkować sztuczne podpięcie.

**Materiał do wykorzystania** — wątki, które nadają się na własną treść, z zaznaczeniem, co w nich ciekawego.

**Do zweryfikowania** — gdzie autor zgaduje, projektuje albo upraszcza. Tu idą też projekcje podane jako liczby, błędy w oryginale i tezy podane jako fakty. Ta sekcja chroni przed zacytowaniem symulacji jako pomiaru.

Pisz prozą, prostym językiem, bez żargonu, który sam wymaga tłumaczenia. Notatka ma być czytelna za pół roku, gdy kontekst wyparuje.

## 4. Domknięcie

Zmień status w indeksie na `zmapowany` i uzupełnij link do mapowania. Zacommituj wszystko razem — tekst, indeks i mapowanie — z opisem, co doszło. Wypchnij na gałąź roboczą.

W odpowiedzi podsumuj krótko: co weszło do bazy, jaka jest teza artykułu i co najciekawszego wyszło z mapowania. Bez powtarzania całej notatki.

## Kiedy coś nie wychodzi

Brak dostępu do treści to nie porażka do zamaskowania. Powiedz wprost, co się udało pobrać, a co nie, i czego potrzebujesz. Zmapowanie zajawki i nazwanie tego artykułem jest gorsze niż przyznanie, że tekstu nie ma.

Gdy artykuł dubluje coś, co już jest w bazie, powiedz to i zaproponuj dopisanie do istniejącego mapowania zamiast zakładania drugiego wpisu.
