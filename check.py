#!/usr/bin/env python3
"""Controlla le notizie di asroma.com e avvisa su Telegram quando ne esce
una nuova che contiene una parola chiave (di default: biglietti / ticket).
Solo libreria standard, nessuna dipendenza da installare."""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

URL = "https://www.asroma.com/it/notizie"
STATE_FILE = "seen.json"
KEYWORDS = [
    k.strip().lower()
    for k in os.environ.get("KEYWORDS", "bigliett,ticket").split(",")
    if k.strip()
]
ARTICLE_RE = re.compile(r"/it/notizie/(\d+)/([\w\-]+)")


class LinkParser(HTMLParser):
    """Raccoglie i link agli articoli: id -> (url, slug)."""

    def __init__(self):
        super().__init__()
        self.articles = {}

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        m = ARTICLE_RE.search(href)
        if m:
            self.articles[m.group(1)] = (urllib.parse.urljoin(URL, href), m.group(2))


def fetch_articles():
    req = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "it-IT,it;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    parser = LinkParser()
    parser.feed(html)
    return parser.articles


def send_telegram(text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    urllib.request.urlopen(
        f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=30
    )


def load_seen():
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE) as f:
        return json.load(f)


def save_seen(ids):
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(ids, key=int)[-500:], f)


def main():
    articles = fetch_articles()
    if not articles:
        # Sito cambiato o richiesta bloccata: fallisce, così GitHub ti manda una mail.
        print("Nessun articolo trovato: struttura cambiata o accesso bloccato.")
        sys.exit(1)

    seen = load_seen()
    if seen is None:
        # Primo avvio: memorizza quello che c'è già e manda un messaggio di prova.
        send_telegram(
            f"✅ Monitor AS Roma attivo ({len(articles)} notizie già presenti). "
            f"Parole chiave: {', '.join(KEYWORDS)}"
        )
        save_seen(articles.keys())
        return

    seen_set = set(seen)
    for art_id, (url, slug) in articles.items():
        if art_id in seen_set:
            continue
        if any(k in slug.lower() for k in KEYWORDS):
            title = slug.replace("-", " ").capitalize()
            send_telegram(f"🎟️ Nuova notizia sui biglietti!\n{title}\n{url}")
        seen_set.add(art_id)

    save_seen(seen_set)


if __name__ == "__main__":
    main()
