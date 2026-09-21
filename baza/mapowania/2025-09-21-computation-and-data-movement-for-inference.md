# Mapowanie: Computation and Data Movement for Inference

Źródło: Tanj Bennett, SemiAnalysis, 21.09.2025
https://newsletter.semianalysis.com/p/computation-and-data-movement-for
Tekst: `baza/artykuly/2025-09-21-computation-and-data-movement-for-inference.md`

## Teza

Właściwą jednostką analizy inferencji nie jest liczba parametrów, tylko aktywny przepływ modelu zestawiony z hierarchią pamięci, sieci i czasu w maszynie — a architektura MoE daje strukturę, którą sprzęt może odwzorować.

## Struktura

Wstęp o MoE i o tym, co zmienił w ekonomii serwowania. Sekcje 1–3 opisują usługę jako całość: orkiestrację, kolejki, KV cache jako niezmienne bloby w wspólnym magazynie oraz cztery reżimy pracy (prefill, midfill, decode attention, decode experts). Sekcje 4–7 pokazują przepływ danych przez warstwę MoE w prefillu i decode oraz to, że model jest wysokim stosem powtarzalnych grup warstw. Sekcje 8–14 mapują to na sprzęt: rodzaje równoległości, logiczny node, racki, granice przepustowości, głębokość pipeline'u. Sekcje 15–20 dotyczą wydajności i ekonomii: sortowanie tras na gęste paczki ekspertów, słaby zysk z batchowania w decode, scheduling, oscylacje w pętli sprzężenia zwrotnego, spór agregacja kontra dezagregacja, przepustowość pamięci kontra pojemność. Sekcje 21–23 to metoda mapowania, ujęcie czasowe i przykład liczbowy: Kimi K3 na systemach Blackwell. Na koniec podsumowanie.

## Kluczowe ustalenia

Trzy reżimy pracy mają różne wąskie gardła i wolą różne konfiguracje maszyn. Prefill jest ograniczony obliczeniami. Midfill dokleja krótki blok do długiego prefiksu i siedzi pośrodku: dużo arytmetyki, ale i ruchu cache'u rzędu dziesiątek GB. Decode dostaje jeden token na przebieg, więc rządzi nim ruch pamięci wokół KV cache.

KV cache to niezmienne bloby w wspólnej, skalowalnej pamięci, nie plik przypięty do maszyny. Dzięki temu worker jest wybierany po dostępności, a nie dlatego, że ma jedyną kopię kontekstu. HBM to warstwa gorąca i droga — kontekst wchodzi tuż przed użyciem i wychodzi zaraz po.

Batchowanie pomaga nierówno. W prefillu i midfillu router może posortować trasy po ekspertach, więc każdy ekspert ładuje się raz i obsługuje swoją listę tokenów. W decode każde zapytanie wnosi własny cache, więc batchowanie nie podnosi intensywności arytmetycznej attention, a eksperci rzadko się dzielą przy małych batchach. Batch rzędu jednego do pięciu bywa rozsądniejszy niż duże paczki.

Sprzężenie zwrotne potrafi rozhuśtać system. Jeśli wpuszczanie nowej pracy jest bramkowane wprost przez kończenie się zapytań decode, opóźnienie sygnału zamienia zwykłą zmienność w oscylację: fabryka na przemian się zapycha i pustoszeje. Lekarstwo to bufory gotowej pracy, wygładzone sygnały, histereza i rozdzielenie szybkich kontroli lokalnych od wolnych decyzji o rekonfiguracji.

Pojemność i przepustowość pamięci to dwa różne cele, nie jedna skala do maksymalizacji. Dane zarabiają, gdy się poruszają. Pojemność ma wartość do momentu, aż aktywne wagi, KV, aktywacje i zapas mieszczą się wygodnie — powyżej tego punktu dokłada koszt, a nie przychód.

Spór agregacja kontra dezagregacja nie ma jednego zwycięzcy. Dezagregacja pozwala inwestować osobno w maszyny mocne obliczeniowo i mocne pamięciowo. Agregacja usuwa przerwę w harmonogramie i transfer kontekstu między etapami, ale wymaga maszyny dobrej we wszystkim — inaczej wychodzi „taka sobie".

## Liczby i dane

Sto dwadzieścia osiem nowych tokenów po osiem ekspertów daje 1024 przypisania na bank 256 ekspertów — stąd sens sortowania. W całym modelu potrafi być około 15 000 ekspertów we wszystkich warstwach. Przy 72 GPU spiętych blisko, warstwa z 256 ekspertami daje 3–4 eksperty na GPU. Eksperci w SRAM to nawet stukrotnie lepsza energia na bajt niż ładowanie z HBM. Przykład Kimi K3 na B200, B300 i GB200 liczy konfiguracje od 16 do 64 GPU; midfill to 127 tysięcy tokenów w cache plus 1000 doklejonych; większość konfiguracji na granicy Pareto mieści się poniżej mniej więcej 80 GB HBM na GPU. Konteksty agentowe w rzeczywistych śladach dochodzą do 250 tysięcy tokenów dla Opusa 4.8 i miliona dla Fable.

## Co z tego dla mnie

To jest solidna baza pojęciowa pod rozmowy o kosztach i opóźnieniach w produktach AI, które buduję. Trzy rzeczy przekładają się wprost na moją pracę. Po pierwsze, zarządzanie kontekstem jest przewagą konkurencyjną, nie detalem implementacyjnym — a agenty z kompakcjami widać w danych. Po drugie, interaktywne tokeny są warte więcej niż hurtowe, więc mnożenie opóźnienia dla ułamka przepustowości to zły interes; to argument, który da się postawić klientowi. Po trzecie, rozróżnienie prefill / midfill / decode tłumaczy, czemu cache prefiksów i krótkie dopiski potrafią radykalnie zmienić rachunek za agenta.

## Materiał do wykorzystania

Wyjaśnienie, czemu NVIDIA spina 72 GPU tak blisko — bo ruch all-to-all przy routingu do ekspertów tego wymaga. To dobry, konkretny wątek na treść. Drugi: oscylacja jako problem sterowania, nie mocy obliczeniowej — czytelna analogia do każdego systemu kolejkowego. Trzeci: „dane zarabiają, gdy się poruszają" jako rama do rozmowy o kosztach infrastruktury.

## Do zweryfikowania

Wszystkie liczby dla Kimi K3 to projekcje z symulatora SemiAnalysis, nie pomiary — autor mówi to wprost i trzeba to powtarzać przy każdym cytowaniu. Tekst miejscami jest surowy redakcyjnie (literówki, niedokończone zdanie w sekcji o AgentX), więc cytaty warto sprawdzać ze źródłem. Wnioski o przyszłej pamięci 3D i o przewadze przepustowości nad pojemnością to teza autora, nie ustalony fakt. Numeracja podsekcji w ostatniej sekcji jest niespójna w oryginale (22.1–22.4 pod nagłówkiem 23).
