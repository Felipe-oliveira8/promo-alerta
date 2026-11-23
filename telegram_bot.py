"""Envio de mensagens pelo bot do Telegram (Bot API)."""

from __future__ import annotations

import html
import time

import requests

API = "https://api.telegram.org/bot{token}/{metodo}"


class TelegramBot:
    def __init__(self, token: str, chat_id: str | int):
        self.token = token
        self.chat_id = chat_id

    def _chamar(self, metodo: str, **params):
        resp = requests.post(
            API.format(token=self.token, metodo=metodo), json=params, timeout=20
        )
        dados = resp.json()
        if not dados.get("ok"):
            # 429 = muitas mensagens; o Telegram diz quanto esperar
            espera = dados.get("parameters", {}).get("retry_after")
            if espera:
                time.sleep(int(espera) + 1)
                return self._chamar(metodo, **params)
            raise RuntimeError(f"Telegram {metodo} falhou: {dados}")
        return dados["result"]

    def novas_mensagens(self, offset: int) -> tuple[list[dict], int]:
        """Mensagens recebidas pelo bot desde a última leitura.
        Devolve (mensagens, novo_offset). Usar o novo offset na próxima
        chamada confirma ao Telegram que estas já foram lidas."""
        updates = self._chamar(
            "getUpdates", offset=offset, timeout=0, allowed_updates=["message"]
        )
        msgs = [u["message"] for u in updates if "message" in u]
        novo = max((u["update_id"] for u in updates), default=offset - 1) + 1
        return msgs, max(novo, offset)

    def definir_menu(self, comandos: list[tuple[str, str]]):
        self._chamar(
            "setMyCommands",
            commands=[{"command": c, "description": d} for c, d in comandos],
        )

    def enviar(self, texto_html: str, preview: bool = True):
        return self._chamar(
            "sendMessage",
            chat_id=self.chat_id,
            text=texto_html[:4096],
            parse_mode="HTML",
            link_preview_options={"is_disabled": not preview},
        )


def formatar_oferta(nome_alerta: str, oferta, preco: float | None) -> str:
    e = html.escape
    resumo = oferta.texto.strip()
    if len(resumo) > 600:
        resumo = resumo[:600].rsplit(" ", 1)[0] + "…"
    preco_txt = (
        f" — <b>R$ {preco:,.2f}</b>".replace(",", "X").replace(".", ",").replace("X", ".")
        if preco is not None
        else ""
    )
    return (
        f"🔥 <b>{e(nome_alerta)}</b>{preco_txt}\n\n"
        f"{e(resumo)}\n\n"
        f'<a href="{e(oferta.link)}">Ver postagem</a> · {e(oferta.fonte)}'
    )
