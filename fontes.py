"""Fontes de promoções.

Cada fonte devolve uma lista de Oferta. Hoje só existe a fonte de canais
públicos do Telegram (página web https://t.me/s/<canal>, que não exige login).
Para adicionar outra fonte, basta criar uma função que devolva list[Oferta].
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


@dataclass
class Oferta:
    canal: str       # nome do canal, sem @
    num: int         # número da postagem no canal (sempre crescente)
    texto: str       # texto completo da postagem
    link: str        # link para a postagem original
    data: str | None = None  # ISO 8601, ex.: "2026-11-23T19:39:00+00:00"

    @property
    def fonte(self) -> str:
        return f"@{self.canal}"


def parse_canal_telegram(html: str, canal: str) -> list[Oferta]:
    """Extrai as postagens do HTML de https://t.me/s/<canal>."""
    soup = BeautifulSoup(html, "html.parser")
    ofertas: list[Oferta] = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        post = msg["data-post"]  # "canal/12345"
        try:
            num = int(post.rsplit("/", 1)[1])
        except (IndexError, ValueError):
            continue
        corpo = msg.select_one("div.tgme_widget_message_text")
        if corpo is None:
            continue  # postagem só com foto/sticker, sem texto
        # <br> vira quebra de linha para não grudar palavras
        for br in corpo.find_all("br"):
            br.replace_with("\n")
        bruto = corpo.get_text(" ", strip=False)
        linhas = [" ".join(l.split()) for l in bruto.split("\n")]
        texto = "\n".join(l for l in linhas if l).strip()
        # Links da postagem (o da loja costuma estar aqui). Só acrescenta os
        # que não aparecem no texto (ex.: "Compre aqui" com link escondido).
        links_externos = []
        for a in corpo.select("a[href]"):
            h = a["href"]
            if h.startswith("https://t.me/") or h in texto or h in links_externos:
                continue
            links_externos.append(h)
        if links_externos:
            texto += "\n" + "\n".join(links_externos)
        ofertas.append(
            Oferta(
                canal=canal,
                num=num,
                texto=texto,
                link=f"https://t.me/{post}",
                data=(msg.select_one("time[datetime]") or {}).get("datetime"),
            )
        )
    return ofertas


def buscar_canal_telegram(canal: str, timeout: int = 20) -> list[Oferta]:
    canal = canal.lstrip("@").strip()
    resp = requests.get(
        f"https://t.me/s/{canal}",
        headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return parse_canal_telegram(resp.text, canal)


def coletar(canais: list[str], pausa: float = 1.5) -> tuple[dict[str, list[Oferta]], dict[str, str]]:
    """Coleta de todos os canais. Devolve ({canal: ofertas}, {canal: erro}).
    Um canal com problema não derruba os outros."""
    ofertas: dict[str, list[Oferta]] = {}
    erros: dict[str, str] = {}
    for i, canal in enumerate(canais):
        if i:
            time.sleep(pausa)
        try:
            ofertas[canal] = buscar_canal_telegram(canal)
        except Exception as e:  # noqa: BLE001
            erros[canal] = str(e)
    return ofertas, erros
