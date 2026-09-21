#!/usr/bin/env python3
"""Wyciąga treść artykułu ze strony Substacka do czystego markdowna.

Substack wysyła pełny tekst w HTML nawet dla wpisów płatnych (robi to dla
wyszukiwarek), więc zwykłe pobranie strony często wystarcza.

Użycie:
    python wyciagnij.py <url> [plik-wyjsciowy.md]

Skrypt sam sprawdza, czy tekst nie urywa się w pół zdania, i ostrzega,
gdy wygląda na samą zajawkę.
"""
import html
import re
import subprocess
import sys


def pobierz(url: str) -> str:
    wynik = subprocess.run(
        ["curl", "-sL", "-A", "Mozilla/5.0", url],
        capture_output=True, text=True, check=True,
    )
    return wynik.stdout


def na_markdown(strona: str) -> str:
    start = strona.find('<div class="available-content">')
    if start < 0:
        raise SystemExit("Nie znalazłem bloku treści — strona ma inny układ niż Substack.")
    koniec = strona.find("paywall", start)
    seg = strona[start:koniec if koniec > 0 else len(strona)]

    seg = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", seg, flags=re.S)
    seg = re.sub(r'<img[^>]*?src="([^"]+)"[^>]*>', r"\n\n![](\1)\n\n", seg)
    for n in range(1, 7):
        seg = re.sub(r"<h%d[^>]*>" % n, "\n\n" + "#" * n + " ", seg)
        seg = seg.replace("</h%d>" % n, "\n\n")
    seg = re.sub(r"<li[^>]*>", "\n- ", seg)
    seg = re.sub(r"<p[^>]*>", "\n\n", seg)
    seg = re.sub(r"</p>|</li>|<br[^>]*>", "\n", seg)
    seg = re.sub(r"</?(strong|b)>", "**", seg)
    seg = re.sub(r"</?(em|i)>", "*", seg)

    tekst = html.unescape(re.sub("<[^>]+>", "", seg))
    tekst = re.sub(r"\n{3,}", "\n\n", tekst)
    linie = [l.rstrip() for l in tekst.split("\n")]
    # ostatnia linia bywa obciętym znacznikiem
    while linie and (linie[-1].startswith("<") or not linie[-1]):
        linie.pop()
    return "\n".join(linie).strip()


def ostrzez(tekst: str) -> None:
    if len(tekst) < 4000:
        print(f"UWAGA: tylko {len(tekst)} znaków — to może być sama zajawka.", file=sys.stderr)
    if tekst and tekst[-1] not in ".!?\"')":
        print("UWAGA: tekst urywa się w pół zdania — sprawdź, czy masz całość.", file=sys.stderr)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    url = sys.argv[1]
    tekst = na_markdown(pobierz(url))
    ostrzez(tekst)
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            f.write(tekst + "\n")
        print(f"Zapisano {len(tekst)} znaków do {sys.argv[2]}")
    else:
        print(tekst)


if __name__ == "__main__":
    main()
