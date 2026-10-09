#!/usr/bin/env python3
"""Controlla le notizie di asroma.com e avvisa su Telegram quando ne esce
una nuova che contiene una parola chiave. L'avviso viene ripetuto per
REPEAT esecuzioni consecutive, così è più difficile perderlo.
Solo libreria standard, nessuna dipendenza da installare."""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

URL = "https://www.asroma.com/it/notizie"
STATE_FILE = "seen.json"
KEYWORDS = [
    k.strip().lower()
    for k in os.environ.get(
        "KEYWORDS", "bigliett,ticket,champions,psg,parigi,paris"
    ).split(",")
    if k.strip()
]
REPEAT = int(os.environ.get("REPEAT", "4"))
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
    token = os.environ["TELEGRAM_BOT_TOKEN"].strip()
    chat_id = os.environ["TELEGRAM_CHAT_ID"].strip()
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=30
        )
    except urllib.error.HTTPError as e:
        print("Telegram ha risposto:", e.read().decode())
        raise


def load_state():
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE) as f:
        data = json.load(f)
    if isinstance(data, list):  # vecchio formato di seen.json
        return {"seen": data, "alerts": {}}
    return data


def save_state(state):
    state["seen"] = sorted(set(state["seen"]), key=int)[-500:]
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def main():
    articles = fetch_articles()
    if not articles:
        # Sito cambiato o richiesta bloccata: fallisce, così GitHub ti manda una mail.
        print("Nessun articolo trovato: struttura cambiata o accesso bloccato.")
        sys.exit(1)

    state = load_state()
    if state is None:
        # Primo avvio: memorizza quello che c'è già e manda un messaggio di prova.
        send_telegram(
            f"✅ Monitor AS Roma attivo ({len(articles)} notizie già presenti). "
            f"Parole chiave: {', '.join(KEYWORDS)}"
        )
        save_state({"seen": list(articles.keys()), "alerts": {}})
        return

    seen = set(state["seen"])
    alerts = state["alerts"]

    # Notizie nuove: se combaciano, entrano nella lista degli avvisi da ripetere.
    for art_id, (url, slug) in articles.items():
        if art_id in seen:
            continue
        seen.add(art_id)
        if any(k in slug.lower() for k in KEYWORDS):
            alerts[art_id] = {"count": 0, "url": url, "slug": slug}

    # Invia (o ripete) gli avvisi finché non raggiungono REPEAT volte.
    for art_id in list(alerts):
        info = alerts[art_id]
        title = info["slug"].replace("-", " ").capitalize()
        n = info["count"] + 1
        send_telegram(
            f"🔔 Nuova notizia AS Roma ({n}/{REPEAT})\n{title}\n{info['url']}"
        )
        info["count"] = n
        if n >= REPEAT:
            del alerts[art_id]

    state["seen"] = list(seen)
    save_state(state)


if __name__ == "__main__":
    main()
