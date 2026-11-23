"""Histórico de preços: busca ofertas antigas nos canais e calcula estatísticas.

Os canais públicos do Telegram aceitam busca na versão web:
  https://t.me/s/<canal>?q=<termo>            → ofertas mais recentes com o termo
  https://t.me/s/<canal>?q=<termo>&before=N   → ofertas mais antigas que a N
Os preços vêm das PROMOÇÕES postadas nos canais, não do preço normal de loja.
"""

from __future__ import annotations

import html
import re
import statistics
import time
from datetime import datetime, timedelta, timezone

import requests

from filtro import casa_termos, normalizar, preco_oferta
from fontes import USER_AGENT, Oferta, parse_canal_telegram

MAX_PAGINAS_POR_CANAL = 25  # 20 resultados por página → até 500 ofertas por canal
PAUSA = 1.0

_RE_PERIODO = re.compile(r"^(\d{1,3})\s*(d|dia|dias|m|mes|meses|mês|a|ano|anos|y)$", re.I)
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


# --- período ----------------------------------------------------------------
def parse_periodo(token: str) -> int | None:
    """'3m' → 90, '6meses' → 180, '1a' / '1ano' → 365, '30d' → 30. Senão None."""
    m = _RE_PERIODO.match(token.strip().lower())
    if not m:
        return None
    n, unidade = int(m.group(1)), m.group(2)
    if unidade.startswith("d"):
        dias = n
    elif unidade.startswith("m"):
        dias = n * 30
    else:
        dias = n * 365
    return max(1, min(dias, 730))  # no máximo 2 anos


def descrever_periodo(dias: int) -> str:
    if dias % 365 == 0:
        n = dias // 365
        return f"{n} ano" + ("s" if n > 1 else "")
    if dias % 30 == 0:
        n = dias // 30
        return f"{n} " + ("mês" if n == 1 else "meses")
    return f"{dias} dias"


# --- busca ------------------------------------------------------------------
def termo_de_busca(alerta: dict) -> str:
    """Monta a busca do Telegram (o filtro completo é aplicado depois).
    Se houver um número de modelo ('5060'), busca só por ele; senão usa a
    primeira expressão do alerta ('air fryer')."""
    termos = [normalizar(t) for t in (alerta.get("todas") or alerta.get("alguma") or [])]
    termos = [t for t in termos if t]
    if not termos:
        return ""
    palavras = [p for t in termos for p in t.split()]
    com_numero = [p for p in palavras if any(c.isdigit() for c in p) and len(p) >= 3]
    return max(com_numero, key=len) if com_numero else termos[0]


def _data(o: Oferta) -> datetime | None:
    if not o.data:
        return None
    try:
        d = datetime.fromisoformat(o.data)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def buscar_no_canal(canal: str, consulta: str, desde: datetime, sessao=None) -> list[Oferta]:
    http = sessao or requests
    vistas: dict[int, Oferta] = {}
    antes = None
    for pagina in range(MAX_PAGINAS_POR_CANAL):
        params = {"q": consulta}
        if antes is not None:
            params["before"] = antes
        if pagina:
            time.sleep(PAUSA)
        resp = http.get(
            f"https://t.me/s/{canal}",
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"},
            timeout=20,
        )
        resp.raise_for_status()
        ofertas = parse_canal_telegram(resp.text, canal)
        novas = [o for o in ofertas if o.num not in vistas]
        if not novas:
            break
        for o in novas:
            vistas[o.num] = o
        mais_antiga = min(novas, key=lambda o: o.num)
        d = _data(mais_antiga)
        if d is not None and d < desde:
            break
        antes = mais_antiga.num
    return [o for o in vistas.values() if (_data(o) or desde) >= desde]


# --- estatística --------------------------------------------------------------
def _fmt(valor: float) -> str:
    return f"R$ {valor:,.0f}".replace(",", ".")


def calcular(pontos: list[tuple[datetime, float, Oferta]]) -> dict | None:
    """pontos = [(data, preço, oferta)]. Remove valores fora da curva
    (ex.: parcela ou cupom lido como preço) antes de calcular."""
    if not pontos:
        return None
    mediana_bruta = statistics.median(p for _, p, _ in pontos)
    bons = [x for x in pontos if 0.4 * mediana_bruta <= x[1] <= 2.5 * mediana_bruta]
    if not bons:
        return None
    precos = sorted(p for _, p, _ in bons)
    q1 = statistics.quantiles(precos, n=4)[0] if len(precos) >= 4 else precos[0]
    minimo = min(bons, key=lambda x: x[1])
    ultimo = max(bons, key=lambda x: x[0])
    por_mes: dict[tuple[int, int], list[float]] = {}
    for d, p, _ in bons:
        por_mes.setdefault((d.year, d.month), []).append(p)
    return {
        "n": len(bons),
        "descartados": len(pontos) - len(bons),
        "minimo": minimo,
        "q1": q1,
        "mediana": statistics.median(precos),
        "media": statistics.fmean(precos),
        "maximo": max(precos),
        "ultimo": ultimo,
        "primeira_data": min(d for d, _, _ in bons),
        "por_mes": {k: (statistics.median(v), len(v)) for k, v in sorted(por_mes.items())},
    }


def relatorio(nome: str, dias: int, est: dict | None, canais: list[str], erros: list[str]) -> str:
    e = html.escape
    cab = f"📊 <b>Preços: {e(nome)}</b>\nÚltimos {descrever_periodo(dias)}"
    if not est:
        txt = (f"{cab}\n\nNão encontrei ofertas com preço nesse período nos canais "
               f"({', '.join('@' + c for c in canais)}).\n"
               "Tente um período maior ou termos mais simples.")
    else:
        d_min, p_min, o_min = est["minimo"]
        d_ult, p_ult, o_ult = est["ultimo"]
        linhas = [
            cab + f" · {est['n']} ofertas (desde {est['primeira_data']:%d/%m/%Y})",
            "",
            f"⚖️ <b>Valor justo (mediana): {_fmt(est['mediana'])}</b>",
            f"👍 Bom preço (25% mais baratas): até {_fmt(est['q1'])}",
            f"🏆 Mínimo: {_fmt(p_min)} em {d_min:%d/%m/%y} "
            f'(<a href="{e(o_min.link)}">ver</a>)',
            f"➗ Média: {_fmt(est['media'])}",
            f"📈 Máximo: {_fmt(est['maximo'])}",
            f"🕒 Última: {_fmt(p_ult)} em {d_ult:%d/%m/%y} "
            f'(<a href="{e(o_ult.link)}">ver</a>)',
        ]
        if len(est["por_mes"]) >= 2:
            linhas += ["", "<b>Mediana por mês</b>"]
            for (ano, mes), (med, n) in list(est["por_mes"].items())[-12:]:
                linhas.append(f"{MESES[mes - 1]}/{ano % 100:02d}: {_fmt(med)} ({n})")
        linhas += ["", "<i>Preços de promoções postadas nos canais, não o preço normal de loja.</i>"]
        txt = "\n".join(linhas)
    if erros:
        txt += "\n\n⚠️ Não consegui consultar: " + ", ".join("@" + e(c) for c in erros)
    return txt


def consultar(alerta: dict, dias: int, canais: list[str], buscar=buscar_no_canal) -> str:
    """Busca o histórico em todos os canais e devolve o relatório pronto."""
    consulta = termo_de_busca(alerta)
    nome = alerta.get("texto") or consulta
    if not consulta:
        return "Não consegui montar a busca: faltam palavras no alerta."
    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    filtro_sem_preco = {k: v for k, v in alerta.items() if k != "preco_max"}
    pontos, erros = [], []
    repetidas = set()  # a mesma oferta postada em 2 canais no mesmo dia conta 1 vez
    for i, canal in enumerate(canais):
        if i:
            time.sleep(PAUSA)
        try:
            ofertas = buscar(canal, consulta, desde)
        except Exception:  # noqa: BLE001
            erros.append(canal)
            continue
        for o in ofertas:
            d, p = _data(o), preco_oferta(o.texto)
            if not (d and p and d >= desde and casa_termos(filtro_sem_preco, o.texto)):
                continue
            chave = (d.date(), round(p))
            if chave in repetidas:
                continue
            repetidas.add(chave)
            pontos.append((d, p, o))
    return relatorio(nome, dias, calcular(pontos), canais, erros)
