"""Testes de ponta a ponta com Telegram e canais simulados."""

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as app  # noqa: E402
from fontes import parse_canal_telegram  # noqa: E402
from tests.test_basico import HTML  # noqa: E402

MEU_CHAT = "111"


def post(n, texto):
    return (f'<div class="tgme_widget_message" data-post="achados/{n}">'
            f'<div class="tgme_widget_message_text">{texto}</div>'
            f'<time datetime="2026-11-23T10:{n:02d}:00+00:00" class="time"></time></div>')


class BotFalso:
    def __init__(self):
        self.enviadas = []
        self.fila = []  # mensagens que "você" mandou
        self.offset_visto = []

    def novas_mensagens(self, offset):
        self.offset_visto.append(offset)
        msgs, self.fila = self.fila, []
        ultimo = offset + len(msgs)
        return msgs, ultimo

    def enviar(self, texto, preview=True):
        self.enviadas.append(texto)

    def definir_menu(self, c):
        pass

    def voce_manda(self, texto, chat=MEU_CHAT):
        self.fila.append({"chat": {"id": int(chat)}, "text": texto})


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    raiz = Path(__file__).resolve().parents[1]
    shutil.copy(raiz / "config.json", tmp_path / "config.json")
    (tmp_path / "config.json").write_text(json.dumps({"canais_iniciais": ["@Achados"]}))
    monkeypatch.setattr(app, "PASTA", tmp_path)
    monkeypatch.setenv("TELEGRAM_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", MEU_CHAT)
    monkeypatch.delenv("CHAVE_ALERTAS", raising=False)
    monkeypatch.setattr(sys, "argv", ["main.py"])

    bot = BotFalso()
    monkeypatch.setattr(app, "TelegramBot", lambda t, c: bot)
    estado = {"html": HTML, "erro": None}

    def coletar_falso(canais):
        if estado["erro"]:
            return {}, {c: estado["erro"] for c in canais}
        return {c: parse_canal_telegram(estado["html"], c) for c in canais}, {}

    monkeypatch.setattr(app, "coletar", coletar_falso)
    return tmp_path, bot, estado


def test_fluxo_completo(ambiente):
    pasta, bot, estado = ambiente

    # Rodada 1: instalação → só boas-vindas; canal novo → só se posiciona
    assert app.main() == 0
    assert len(bot.enviadas) == 1 and "instalado" in bot.enviadas[0]
    bot.enviadas.clear()
    assert json.loads((pasta / "dados/posicao.json").read_text())["ultimo"] == {"achados": 103}

    # Rodada 2: você cria um alerta → resposta + busca retroativa na página
    bot.voce_manda('/add "air fryer" -forma max 450')
    assert app.main() == 0
    assert "Alerta criado" in bot.enviadas[0]
    assert len(bot.enviadas) == 2 and "postagem recente" in bot.enviadas[1] and "349,90" in bot.enviadas[1]

    # Rodada 3: postagem nova que casa + uma que não casa
    bot.enviadas.clear()
    estado["html"] = HTML + post(104, "Air Fryer Electrolux R$ 299,00") + post(105, "Air fryer R$ 999,00")
    assert app.main() == 0
    assert len(bot.enviadas) == 1 and "R$ 299,00" in bot.enviadas[0]
    assert "postagem recente" not in bot.enviadas[0]

    # Rodada 4: nada novo → nada enviado (sem duplicar)
    bot.enviadas.clear()
    assert app.main() == 0
    assert bot.enviadas == []

    # Estranho tentando comandar o bot → ignorado
    bot.voce_manda("/remover 1", chat="999")
    assert app.main() == 0
    assert bot.enviadas == []
    bot.voce_manda("/lista")
    assert app.main() == 0
    assert "#1" in bot.enviadas[-1] and "air fryer" in bot.enviadas[-1]

    # Pausar → postagem nova não é enviada
    bot.voce_manda("/pausar 1")
    app.main()
    bot.enviadas.clear()
    estado["html"] += post(106, "Air Fryer Mondial R$ 199,00")
    app.main()
    assert bot.enviadas == []


def test_limite_retroativo(ambiente):
    pasta, bot, estado = ambiente
    estado["html"] = "".join(post(n, f"Air fryer modelo {n}") for n in range(1, 21))
    app.main()
    bot.enviadas.clear()
    bot.voce_manda("/add air fryer")
    app.main()
    assert len(bot.enviadas) == 1 + app.LIMITE_RETRO
    # As mais recentes (16 a 20), não as mais antigas
    assert "modelo 20" in bot.enviadas[-1] and "modelo 16" in bot.enviadas[1]
    assert not any("modelo 1\n" in m for m in bot.enviadas)


def test_canal_com_erro_avisa(ambiente):
    pasta, bot, estado = ambiente
    app.main()  # posiciona
    estado["erro"] = "404"
    for _ in range(app.AVISAR_APOS_FALHAS + 2):
        app.main()
    avisos = [m for m in bot.enviadas if "Não estou conseguindo ler" in m]
    assert len(avisos) == 1


def test_canais_por_comando(ambiente):
    pasta, bot, estado = ambiente
    bot.voce_manda("/addcanal https://t.me/s/OfertasKabum")
    bot.voce_manda("/rmcanal @achados")
    bot.voce_manda("/canais")
    app.main()
    assert "@ofertaskabum" in bot.enviadas[-1] and "@achados" not in bot.enviadas[-1]


def test_alertas_criptografados(ambiente, monkeypatch):
    from cryptography.fernet import Fernet

    pasta, bot, estado = ambiente
    monkeypatch.setenv("CHAVE_ALERTAS", Fernet.generate_key().decode())
    bot.voce_manda("/add segredo-xyz")
    app.main()
    bruto = (pasta / "dados/alertas.enc").read_bytes()
    assert b"segredo" not in bruto and not (pasta / "dados/alertas.json").exists()
    # Relê com a mesma chave
    bot.voce_manda("/lista")
    app.main()
    assert "segredo-xyz" in bot.enviadas[-1]
    # Sem mudanças, o arquivo não é regravado (evita commits à toa)
    antes = (pasta / "dados/alertas.enc").read_bytes()
    app.main()
    assert (pasta / "dados/alertas.enc").read_bytes() == antes
