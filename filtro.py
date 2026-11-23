"""Filtro por palavra-chave, exclusões e preço máximo."""

from __future__ import annotations

import re
import unicodedata

# Preço em reais. Aceita "R$ 2.499,00", "R$2499,00", "R$ 2170,00", "R$ 349,90", "R$ 50".
# A 1ª alternativa exige separador de milhar; a 2ª pega números sem ponto.
_RE_PRECO = re.compile(
    r"R\$\s*(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)(?![\d.,]*\d)", re.I
)

# Trechos com valores que NÃO são o preço do produto (parcelas, cupons, cashback...)
_RE_NAO_PRECO = re.compile(
    r"\d+\s*x\s*(?:de\s*)?R\$\s*[\d.,]+"                              # 12x de R$ 250
    r"|R\$\s*[\d.,]+\s*(?:off\b|de\s+desconto|desconto|de\s+cashback|cashback|de\s+volta)"
    r"|(?:economi[sz]e|desconto\s+de|cashback\s+de|cupom\s+de|frete\s*(?:de|:)?)\s*R\$\s*[\d.,]+"
    r"|(?:acima\s+de|a\s+partir\s+de\s+compras\s+de|compras\s+acima\s+de)\s*R\$\s*[\d.,]+",
    re.I,
)


def normalizar(texto: str) -> str:
    """minúsculas, sem acentos, só letras/números e espaços simples.
    Separa letras de números, então "RTX5060Ti", "5060-Ti" e "5060 Ti"
    viram todos "rtx 5060 ti"; "16GB" e "16 GB" viram "16 gb"."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    texto = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _para_float(bruto: str) -> float | None:
    try:
        return float(bruto.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def extrair_precos(texto: str) -> list[float]:
    """Todos os valores em R$ do texto, na ordem."""
    return [p for p in (_para_float(b) for b in _RE_PRECO.findall(texto)) if p is not None]


def preco_oferta(texto: str) -> float | None:
    """Melhor palpite do preço do produto: o menor valor em R$, ignorando
    parcelas, cupons, cashback e frete."""
    precos = extrair_precos(_RE_NAO_PRECO.sub(" ", texto))
    precos = [p for p in precos if p > 0]
    return min(precos) if precos else None


def _contem(texto_norm: str, termo: str) -> bool:
    """Busca o termo como palavra(s) inteira(s): 'tv' não casa com 'tvbox'."""
    termo_norm = normalizar(termo)
    if not termo_norm:
        return False
    padrao = r"(?<![a-z0-9])" + re.escape(termo_norm) + r"(?![a-z0-9])"
    return re.search(padrao, texto_norm) is not None


def casa_termos(alerta: dict, texto: str) -> bool:
    """Só as palavras (todas / alguma / excluir), sem olhar preço."""
    t = normalizar(texto)
    if not all(_contem(t, p) for p in alerta.get("todas", [])):
        return False
    alguma = alerta.get("alguma") or []
    if alguma and not any(_contem(t, p) for p in alguma):
        return False
    if any(_contem(t, p) for p in alerta.get("excluir", [])):
        return False
    return True


def casa(alerta: dict, texto: str) -> tuple[bool, float | None]:
    """Devolve (casou?, preço encontrado ou None).

    Campos do alerta (todos opcionais exceto 'todas'):
      todas:     todas estas palavras precisam aparecer
      alguma:    pelo menos uma destas precisa aparecer (se a lista existir)
      excluir:   nenhuma destas pode aparecer
      preco_max: se definido, exige um preço <= este valor no texto
    """
    if not casa_termos(alerta, texto):
        return False, None
    preco = preco_oferta(texto)
    preco_max = alerta.get("preco_max")
    if preco_max is not None:
        # Sem preço no texto: não dá pra garantir → descarta.
        if preco is None or preco > float(preco_max):
            return False, preco
    return True, preco
