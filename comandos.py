"""Comandos que você manda para o bot no Telegram.

Como o robô roda de tempos em tempos (não fica ligado direto), os comandos
são lidos no começo de cada rodada — a resposta pode levar até ~10 minutos.
"""

from __future__ import annotations

import html
import re
import shlex

from estado import Alertas

AJUDA = """<b>Promo Alerta</b> — comandos

<b>/add</b> palavras — cria um alerta
  • todas as palavras precisam aparecer
  • <code>"air fryer"</code> entre aspas = expressão exata
  • <code>mondial|philco</code> = pelo menos uma delas
  • <code>-forma</code> = não pode aparecer
  • <code>max 400</code> = só até R$ 400
  Ex.: <code>/add "air fryer" mondial|philco -forma -capa max 450</code>

<b>/lista</b> — mostra seus alertas
<b>/remover</b> N — apaga o alerta N (ou vários: <code>/remover 2 3 4</code>)
<b>/remover tudo</b> — apaga todos (pede confirmação)
<b>/pausar</b> N · <b>/ativar</b> N — pausa/retoma o alerta N

<b>/preco</b> N período — valor justo e histórico de preço do alerta N
  • período: <code>30d</code>, <code>3m</code>, <code>6m</code>, <code>1a</code> (padrão: 3m)
  Ex.: <code>/preco 1 6m</code> ou <code>/preco "5060 ti" 16gb 1a</code>

<b>/canais</b> — canais monitorados
<b>/addcanal</b> @canal · <b>/rmcanal</b> @canal

Respostas chegam na próxima rodada (até ~10 min)."""

COMANDOS_MENU = [
    ("add", "Criar alerta: /add \"air fryer\" -forma max 400"),
    ("lista", "Ver meus alertas"),
    ("remover", "Apagar: /remover N, /remover 2 3, /remover tudo"),
    ("pausar", "Pausar alerta: /pausar N"),
    ("ativar", "Reativar alerta: /ativar N"),
    ("preco", "Valor justo e histórico: /preco N 6m"),
    ("canais", "Ver canais monitorados"),
    ("addcanal", "Monitorar canal: /addcanal @canal"),
    ("rmcanal", "Parar de monitorar: /rmcanal @canal"),
    ("ajuda", "Como usar"),
]

_RE_PRECO = re.compile(r"^(?:<=?|r\$)?(\d+(?:[.,]\d{1,2})?)$", re.I)
_RE_CANAL = re.compile(r"^@?(?:https?://)?(?:t\.me/(?:s/)?)?@?([A-Za-z][A-Za-z0-9_]{3,31})/?$")


def parse_alerta(texto: str) -> dict:
    """Converte o texto do /add num alerta. Levanta ValueError se ficar vazio."""
    # Aspas "inteligentes" do celular viram aspas normais
    texto = texto.replace("“", '"').replace("”", '"').replace("„", '"')
    try:
        tokens = shlex.split(texto)
    except ValueError:  # aspas sem fechar
        tokens = texto.replace('"', " ").split()

    todas, alguma, excluir = [], [], []
    preco_max = None
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        baixo = tok.lower()
        if baixo in ("max", "ate", "até", "maximo", "máximo") and i + 1 < len(tokens):
            m = _RE_PRECO.match(tokens[i + 1].lower())
            if m:
                preco_max = float(m.group(1).replace(",", "."))
                i += 2
                continue
        m = _RE_PRECO.match(baixo) if baixo.startswith(("<", "r$")) else None
        if m:
            preco_max = float(m.group(1).replace(",", "."))
        elif tok.startswith("-") and len(tok) > 1:
            excluir.append(tok[1:])
        elif "|" in tok:
            alguma.extend(p for p in tok.split("|") if p)
        else:
            todas.append(tok)
        i += 1

    if not todas and not alguma:
        raise ValueError("faltou dizer o que procurar")
    return {
        "texto": texto.strip(),
        "todas": todas,
        "alguma": alguma,
        "excluir": excluir,
        "preco_max": preco_max,
    }


def descrever(a: dict) -> str:
    e = html.escape
    partes = [" + ".join(f"<b>{e(t)}</b>" for t in a["todas"])] if a["todas"] else []
    if a.get("alguma"):
        partes.append("(" + " ou ".join(e(t) for t in a["alguma"]) + ")")
    if a.get("excluir"):
        partes.append("sem " + ", ".join(e(t) for t in a["excluir"]))
    if a.get("preco_max") is not None:
        partes.append(f"até R$ {a['preco_max']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    pausa = " ⏸️ <i>pausado</i>" if not a.get("ativo", True) else ""
    return f"<b>#{a['id']}</b> " + " · ".join(partes) + pausa


def _numero(arg: str) -> int | None:
    arg = arg.strip().lstrip("#")
    return int(arg) if arg.isdigit() else None


PERIODO_PADRAO = 90


def separar_periodo(arg: str) -> tuple[str, int]:
    """'1 6m' → ('1', 180); '"5060 ti" 16gb 1 ano' → ('"5060 ti" 16gb', 365)."""
    from historico import parse_periodo

    partes = arg.split()
    if len(partes) >= 1:
        dias = parse_periodo(partes[-1])
        if dias:
            return " ".join(partes[:-1]), dias
    if len(partes) >= 2:
        dias = parse_periodo(partes[-2] + partes[-1])  # "1 ano", "6 meses"
        if dias:
            return " ".join(partes[:-2]), dias
    return arg, PERIODO_PADRAO


def executar(texto: str, alertas: Alertas, consultar_preco=None) -> tuple[str | None, list[dict]]:
    """Executa um comando. Devolve (resposta, alertas_criados_agora).
    consultar_preco(alerta, dias) -> str é usado pelo /preco."""
    texto = texto.strip()
    if not texto.startswith("/"):
        return "Não entendi. Mande /ajuda para ver os comandos.", []
    cmd, _, arg = texto.partition(" ")
    cmd = cmd[1:].split("@", 1)[0].lower()  # "/add@MeuBot" → "add"
    arg = arg.strip()

    if cmd in ("start", "ajuda", "help"):
        return AJUDA, []

    if cmd == "add":
        if not arg:
            return 'Uso: <code>/add "air fryer" -forma max 400</code>', []
        try:
            novo = alertas.adicionar(parse_alerta(arg))
        except ValueError as e:
            return f"Não consegui criar o alerta: {html.escape(str(e))}.", []
        return (
            "✅ Alerta criado:\n" + descrever(novo)
            + "\n\nVou conferir também as postagens recentes dos canais.",
            [novo],
        )

    if cmd == "lista":
        if not alertas.alertas:
            return "Você ainda não tem alertas. Crie um com /add.", []
        return "Seus alertas:\n\n" + "\n".join(descrever(a) for a in alertas.alertas), []

    if cmd == "remover" and arg.lower().split()[:1] in (["tudo"], ["todos"]):
        total = len(alertas.alertas)
        if not total:
            return "Você não tem alertas para apagar.", []
        if arg.lower().split()[1:2] != ["sim"]:
            return (f"⚠️ Isso apaga <b>todos os {total} alertas</b> e não dá para desfazer.\n"
                    "Para confirmar, mande: <code>/remover tudo sim</code>"), []
        for a in list(alertas.alertas):
            alertas.remover(a["id"])
        return f"🗑️ Pronto: {total} alerta(s) apagado(s). Crie novos com /add.", []

    if cmd == "remover" and len(arg.replace(",", " ").split()) > 1:
        numeros = [_numero(p) for p in arg.replace(",", " ").split()]
        if None in numeros:
            return "Uso: <code>/remover 2 3 4</code> (números de /lista) ou <code>/remover tudo</code>", []
        apagados = [n for n in numeros if alertas.remover(n)]
        faltando = [n for n in numeros if n not in apagados]
        txt = (f"🗑️ Apagados: {', '.join('#' + str(n) for n in apagados)}." if apagados
               else "Nenhum alerta apagado.")
        if faltando:
            txt += f"\nNão achei: {', '.join('#' + str(n) for n in faltando)}."
        return txt, []

    if cmd in ("remover", "pausar", "ativar"):
        n = _numero(arg)
        if n is None:
            return f"Uso: <code>/{cmd} N</code> (veja os números em /lista)", []
        if cmd == "remover":
            a = alertas.remover(n)
            return (f"🗑️ Alerta #{n} removido." if a else f"Não achei o alerta #{n}."), []
        a = alertas.definir_ativo(n, cmd == "ativar")
        if not a:
            return f"Não achei o alerta #{n}.", []
        return ("▶️ " if cmd == "ativar" else "⏸️ ") + descrever(a), []

    if cmd in ("preco", "preço", "precos"):
        resto, dias = separar_periodo(arg)
        if not resto:
            return 'Uso: <code>/preco N 6m</code> (N de /lista) ou <code>/preco "5060 ti" 16gb 1a</code>', []
        n = _numero(resto)
        if n is not None and " " not in resto.strip():
            alerta = alertas.buscar(n)
            if not alerta:
                return f"Não achei o alerta #{n}. Veja os números em /lista.", []
        else:
            try:
                alerta = parse_alerta(resto)
            except ValueError as e:
                return f"Não entendi o produto: {html.escape(str(e))}.", []
        if consultar_preco is None:
            return "Consulta de preços indisponível agora.", []
        return consultar_preco(alerta, dias), []

    if cmd == "canais":
        if not alertas.canais:
            return "Nenhum canal. Adicione com /addcanal @canal", []
        return "Canais monitorados:\n" + "\n".join(f"• @{html.escape(c)}" for c in alertas.canais), []

    if cmd in ("addcanal", "rmcanal"):
        m = _RE_CANAL.match(arg)
        if not m:
            return f"Uso: <code>/{cmd} @nome_do_canal</code>", []
        canal = m.group(1).lower()
        if cmd == "addcanal":
            ok = alertas.adicionar_canal(canal)
            return (
                f"✅ @{canal} adicionado. Se ele não for um canal público, aviso aqui."
                if ok else f"@{canal} já estava na lista."
            ), []
        ok = alertas.remover_canal(canal)
        return (f"🗑️ @{canal} removido." if ok else f"@{canal} não estava na lista."), []

    return "Comando desconhecido. Mande /ajuda.", []
