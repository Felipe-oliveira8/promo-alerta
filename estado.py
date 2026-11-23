"""Armazenamento do Promo Alerta.

Duas partes, com cuidados diferentes:

1. Alertas e canais (dados/alertas.enc)
   Mudam pouco (só quando você usa /add, /remover...). Ficam no repositório,
   CRIPTOGRAFADOS com a chave CHAVE_ALERTAS (guardada nos Secrets do GitHub).
   Sem a chave (ex.: testando no PC) usa dados/alertas.json em texto puro.

2. Posição de leitura (dados/posicao.json)
   Último número de postagem lido em cada canal + posição das mensagens do
   bot. Muda a cada rodada, não é sensível e fica no cache do GitHub Actions.
   Se for perdida, a próxima rodada só "se recoloca" em silêncio.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

RESALVAR_APOS_DIAS = 30  # mantém o repositório "ativo" para o GitHub


def _gravar_atomico(caminho: Path, conteudo: bytes):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_bytes(conteudo)
    os.replace(tmp, caminho)


class Alertas:
    def __init__(self, pasta: Path, chave: str | None, canais_iniciais: list[str]):
        self.chave = chave
        self.caminho = pasta / ("alertas.enc" if chave else "alertas.json")
        self.alertas: list[dict] = []
        self.canais: list[str] = []
        self.salvo_em: float = 0
        self.mudou = False
        self.primeira_vez = not self.caminho.exists()
        if not self.primeira_vez:
            dados = json.loads(self._ler())
            self.alertas = dados.get("alertas", [])
            self.canais = dados.get("canais", [])
            self.salvo_em = dados.get("salvo_em", 0)
        else:
            self.canais = [c.lstrip("@").lower() for c in canais_iniciais]
            self.mudou = True
        if time.time() - self.salvo_em > RESALVAR_APOS_DIAS * 86400:
            self.mudou = True

    # --- cripto -----------------------------------------------------------
    def _fernet(self):
        from cryptography.fernet import Fernet

        return Fernet(self.chave.encode())

    def _ler(self) -> str:
        bruto = self.caminho.read_bytes()
        if self.chave:
            return self._fernet().decrypt(bruto).decode("utf-8")
        return bruto.decode("utf-8")

    def salvar_se_mudou(self) -> bool:
        if not self.mudou:
            return False
        self.salvo_em = time.time()
        texto = json.dumps(
            {"alertas": self.alertas, "canais": self.canais, "salvo_em": self.salvo_em},
            ensure_ascii=False,
            indent=1,
        ).encode("utf-8")
        _gravar_atomico(self.caminho, self._fernet().encrypt(texto) if self.chave else texto)
        self.mudou = False
        return True

    # --- operações --------------------------------------------------------
    def ativos(self) -> list[dict]:
        return [a for a in self.alertas if a.get("ativo", True)]

    def adicionar(self, alerta: dict) -> dict:
        alerta["id"] = max((a["id"] for a in self.alertas), default=0) + 1
        alerta.setdefault("ativo", True)
        self.alertas.append(alerta)
        self.mudou = True
        return alerta

    def buscar(self, id_: int) -> dict | None:
        return next((a for a in self.alertas if a["id"] == id_), None)

    def remover(self, id_: int) -> dict | None:
        a = self.buscar(id_)
        if a:
            self.alertas.remove(a)
            self.mudou = True
        return a

    def definir_ativo(self, id_: int, ativo: bool) -> dict | None:
        a = self.buscar(id_)
        if a and a.get("ativo", True) != ativo:
            a["ativo"] = ativo
            self.mudou = True
        return a

    def adicionar_canal(self, canal: str) -> bool:
        canal = canal.lstrip("@").lower()
        if canal in self.canais:
            return False
        self.canais.append(canal)
        self.mudou = True
        return True

    def remover_canal(self, canal: str) -> bool:
        canal = canal.lstrip("@").lower()
        if canal not in self.canais:
            return False
        self.canais.remove(canal)
        self.mudou = True
        return True


class Posicao:
    def __init__(self, caminho: Path):
        self.caminho = caminho
        dados = {}
        if caminho.exists():
            try:
                dados = json.loads(caminho.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                dados = {}
        self.ultimo: dict[str, int] = dados.get("ultimo", {})
        self.falhas: dict[str, int] = dados.get("falhas", {})
        self.update_offset: int = dados.get("update_offset", 0)
        self.menu: str = dados.get("menu", "")  # versão do menu de comandos já cadastrada

    def salvar(self):
        _gravar_atomico(
            self.caminho,
            json.dumps(
                {"ultimo": self.ultimo, "falhas": self.falhas,
                 "update_offset": self.update_offset, "menu": self.menu},
                indent=1,
            ).encode("utf-8"),
        )
