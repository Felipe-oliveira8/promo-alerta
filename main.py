"""Promo Alerta — avisa no Telegram quando uma promoção casa com seus alertas.

Uso:
  python main.py                # uma rodada: lê comandos, coleta, filtra, envia
  python main.py --simular      # mostra no terminal o que enviaria (não envia nada)
  python main.py --configurar   # testa o bot e cadastra o menu de comandos
  python main.py --gerar-chave  # cria uma CHAVE_ALERTAS nova
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from comandos import COMANDOS_MENU, executar
from estado import Alertas, Posicao
from filtro import casa
from fontes import coletar
from telegram_bot import TelegramBot, formatar_oferta

PASTA = Path(__file__).resolve().parent
AVISAR_APOS_FALHAS = 6  # ~1h com rodadas a cada 10 min
LIMITE_RETRO = 5  # resultados antigos por alerta recém-criado


def carregar_env(caminho: Path):
    """Lê CHAVE=valor de um arquivo .env (sem depender de bibliotecas)."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


def processar_comandos(bot: TelegramBot, posicao: Posicao, alertas: Alertas, chat_id: str) -> list[dict]:
    """Lê e responde os comandos novos. Devolve os alertas criados agora."""
    msgs, posicao.update_offset = bot.novas_mensagens(posicao.update_offset)
    criados: list[dict] = []
    for msg in msgs:
        # Segurança: só obedece ao SEU chat. Qualquer outra pessoa é ignorada.
        if str(msg.get("chat", {}).get("id")) != str(chat_id):
            continue
        resposta, novos = executar(msg.get("text", ""), alertas)
        criados.extend(novos)
        if resposta:
            bot.enviar(resposta, preview=False)
    return criados


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--configurar", action="store_true")
    ap.add_argument("--gerar-chave", action="store_true")
    args = ap.parse_args()

    if args.gerar_chave:
        from cryptography.fernet import Fernet

        print(Fernet.generate_key().decode())
        return 0

    carregar_env(PASTA / ".env")
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    chave = os.environ.get("CHAVE_ALERTAS") or None
    if not args.simular and not (token and chat_id):
        print("Defina TELEGRAM_TOKEN e TELEGRAM_CHAT_ID (arquivo .env ou Secrets).")
        return 2
    bot = TelegramBot(token, chat_id) if token and chat_id else None

    if args.configurar:
        bot.definir_menu(COMANDOS_MENU)
        bot.enviar("✅ Promo Alerta conectado!\nMande /ajuda para ver os comandos.")
        print("Bot configurado e mensagem de teste enviada.")
        return 0

    config = json.loads((PASTA / "config.json").read_text(encoding="utf-8"))
    dados = PASTA / "dados"
    alertas = Alertas(dados, chave, config.get("canais_iniciais", []))
    posicao = Posicao(dados / "posicao.json")

    def avisar(msg: str, preview: bool = True):
        if args.simular or bot is None:
            print("-" * 60 + "\n" + msg)
        else:
            bot.enviar(msg, preview=preview)

    # 0) Primeira execução: cadastra o menu de comandos e dá boas-vindas
    if alertas.primeira_vez and bot and not args.simular:
        bot.definir_menu(COMANDOS_MENU)
        bot.enviar("✅ Promo Alerta instalado e funcionando!\n\n"
                   "Crie seu primeiro alerta, por exemplo:\n"
                   '<code>/add "air fryer" -forma max 450</code>\n\n'
                   "Mande /ajuda para ver todos os comandos.", preview=False)

    # 1) Comandos que você mandou para o bot
    criados = []
    if bot and not args.simular:
        criados = processar_comandos(bot, posicao, alertas, chat_id)
    ids_novos = {a["id"] for a in criados}

    # 2) Coleta
    por_canal, erros = coletar(alertas.canais)

    # 3) Filtro e envio
    enviadas = 0
    # Postagens já existentes que casam com alertas criados agora: {id: [(oferta, preço)]}
    retro: dict[int, list] = {}
    ativos = alertas.ativos()
    for canal, ofertas in por_canal.items():
        ultimo = posicao.ultimo.get(canal)
        for oferta in sorted(ofertas, key=lambda o: o.num):
            eh_nova = ultimo is not None and oferta.num > ultimo
            if args.simular or eh_nova:
                candidatos = ativos
            else:
                candidatos = [a for a in ativos if a["id"] in ids_novos]
            for alerta in candidatos:
                ok, preco = casa(alerta, oferta.texto)
                if not ok:
                    continue
                if args.simular or eh_nova:
                    avisar(formatar_oferta(f"#{alerta['id']} {alerta['texto']}", oferta, preco))
                    enviadas += 1
                else:
                    retro.setdefault(alerta["id"], []).append((oferta, preco))
                break  # uma mensagem por postagem
        if ofertas:
            posicao.ultimo[canal] = max([o.num for o in ofertas] + [ultimo or 0])
        posicao.falhas.pop(canal, None)

    # 3b) Para alertas recém-criados: as LIMITE_RETRO postagens mais recentes
    for id_, achados in retro.items():
        alerta = alertas.buscar(id_)
        achados.sort(key=lambda par: par[0].data or "")
        for oferta, preco in achados[-LIMITE_RETRO:]:
            rotulo = f"#{id_} {alerta['texto']} (postagem recente)"
            avisar(formatar_oferta(rotulo, oferta, preco))
            enviadas += 1

    # 4) Canais com problema: avisa uma vez quando passa do limite
    for canal, erro in erros.items():
        n = posicao.falhas.get(canal, 0) + 1
        posicao.falhas[canal] = n
        print(f"AVISO: @{canal} falhou ({n}x seguidas): {erro}", file=sys.stderr)
        if n == AVISAR_APOS_FALHAS or (n == 1 and canal not in posicao.ultimo):
            avisar(
                f"⚠️ Não estou conseguindo ler @{canal} ({n}x seguidas). "
                "Confira se ele é um canal público; para tirar da lista: "
                f"/rmcanal @{canal}",
                preview=False,
            )

    # Esquece posições de canais removidos
    for canal in list(posicao.ultimo):
        if canal not in alertas.canais:
            posicao.ultimo.pop(canal)
            posicao.falhas.pop(canal, None)

    if not args.simular:
        alertas.salvar_se_mudou()
        posicao.salvar()

    total = sum(len(v) for v in por_canal.values())
    print(f"{total} postagens lidas em {len(por_canal)} canal(is), "
          f"{enviadas} alerta(s) enviado(s), {len(erros)} canal(is) com erro.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
