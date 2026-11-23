"""Filtro por palavra-chave, exclusões e preço máximo."""

from __future__ import annotations

import re
import unicodedata

_RE_PRECO = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)")


def normalizar(texto: str) -> str:
    """minúsculas, sem acentos, espaços simples."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto.lower()).strip()


def extrair_precos(texto: str) -> list[float]:
    precos = []
    for bruto in _RE_PRECO.findall(texto):
        try:
            precos.append(float(bruto.replace(".", "").replace(",", ".")))
        except ValueError:
            pass
    return precos


def _contem(texto_norm: str, termo: str) -> bool:
    """Busca o termo como palavra(s) inteira(s): 'tv' não casa com 'tvbox'."""
    termo_norm = normalizar(termo)
    if not termo_norm:
        return False
    padrao = r"(?<![a-z0-9])" + re.escape(termo_norm) + r"(?![a-z0-9])"
    return re.search(padrao, texto_norm) is not None


def casa(alerta: dict, texto: str) -> tuple[bool, float | None]:
    """Devolve (casou?, menor preço encontrado ou None).

    Campos do alerta (todos opcionais exceto 'todas'):
      todas:     todas estas palavras precisam aparecer
      alguma:    pelo menos uma destas precisa aparecer (se a lista existir)
      excluir:   nenhuma destas pode aparecer
      preco_max: se definido, exige um preço <= este valor no texto
    """
    t = normalizar(texto)

    if not all(_contem(t, p) for p in alerta.get("todas", [])):
        return False, None
    alguma = alerta.get("alguma") or []
    if alguma and not any(_contem(t, p) for p in alguma):
        return False, None
    if any(_contem(t, p) for p in alerta.get("excluir", [])):
        return False, None

    precos = extrair_precos(texto)
    menor = min(precos) if precos else None
    preco_max = alerta.get("preco_max")
    if preco_max is not None:
        # Sem preço no texto: não dá pra garantir → descarta.
        if menor is None or menor > float(preco_max):
            return False, menor
    return True, menor
