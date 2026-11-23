import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comandos import parse_alerta  # noqa: E402
from filtro import casa, extrair_precos, normalizar  # noqa: E402
from fontes import parse_canal_telegram  # noqa: E402
from telegram_bot import formatar_oferta  # noqa: E402

HTML = """
<div class="tgme_widget_message_wrap">
 <div class="tgme_widget_message" data-post="achados/101">
  <div class="tgme_widget_message_text">🔥 Fritadeira <b>Air Fryer</b> Mondial 4L<br>Por R$ 349,90 à vista<br>
   <a href="https://www.loja.com.br/p/123">https://www.loja.com.br/p/123</a></div>
 </div>
</div>
<div class="tgme_widget_message_wrap">
 <div class="tgme_widget_message" data-post="achados/102">
  <div class="tgme_widget_message_text">Forma de silicone para air fryer R$ 19,90
   <a href="https://loja.com/x">Compre aqui</a></div>
 </div>
</div>
<div class="tgme_widget_message_wrap">
 <div class="tgme_widget_message" data-post="achados/103">
  <div class="tgme_widget_message_text">Air Fryer Philco 12L — R$ 1.299,00</div>
 </div>
</div>
<div class="tgme_widget_message_wrap">
 <div class="tgme_widget_message" data-post="achados/104"><div class="tgme_widget_message_photo_wrap"></div></div>
</div>
"""

ALERTA = {
    "todas": ["air fryer"],
    "excluir": ["forma", "capa"],
    "preco_max": 450,
}


def test_parser():
    ofs = parse_canal_telegram(HTML, "achados")
    assert [o.num for o in ofs] == [101, 102, 103]
    assert ofs[0].link == "https://t.me/achados/101" and ofs[0].fonte == "@achados"
    assert ofs[0].texto == "🔥 Fritadeira Air Fryer Mondial 4L\nPor R$ 349,90 à vista\nhttps://www.loja.com.br/p/123"
    assert ofs[1].texto.endswith("Compre aqui\nhttps://loja.com/x")  # link escondido é revelado


def test_filtro():
    ofs = parse_canal_telegram(HTML, "achados")
    resultados = [casa(ALERTA, o.texto) for o in ofs]
    assert resultados[0] == (True, 349.90)
    assert resultados[1][0] is False  # excluída por "forma"
    assert resultados[2] == (False, 1299.0)  # acima do preço máximo


def test_normalizacao_e_palavra_inteira():
    assert normalizar("  Promoção  ÁÉÍ ") == "promocao aei"
    assert casa({"todas": ["tv"]}, "Smart TV 50") == (True, None)
    assert casa({"todas": ["tv"]}, "TVBox 4K")[0] is False
    assert casa({"todas": ["promocao"]}, "PROMOÇÃO relâmpago")[0] is True


def test_precos():
    assert extrair_precos("de R$ 2.499,00 por R$1.999,90 ou R$ 50") == [2499.0, 1999.9, 50.0]
    assert extrair_precos("Por R$ 3.229 em até 12X") == [3229.0]
    assert extrair_precos("Por: R$ 5.599,00 à vista no PIX") == [5599.0]


def test_alguma():
    a = {"todas": ["air fryer"], "alguma": ["mondial", "electrolux"]}
    assert casa(a, "Air fryer Mondial")[0]
    assert not casa(a, "Air fryer Philco")[0]


def test_formatacao_escapa_html():
    ofs = parse_canal_telegram(HTML, "achados")
    ofs[0].texto += " <script>"
    msg = formatar_oferta("#1 air fryer", ofs[0], 349.9)
    assert "R$ 349,90" in msg and "&lt;script&gt;" in msg


def test_parse_alerta():
    a = parse_alerta('“air fryer” mondial|philco -forma -capa max 450')
    assert a["todas"] == ["air fryer"]
    assert a["alguma"] == ["mondial", "philco"]
    assert a["excluir"] == ["forma", "capa"]
    assert a["preco_max"] == 450.0
    assert parse_alerta("iphone 15 <=3500,50")["preco_max"] == 3500.5
    assert parse_alerta("iphone 15 até 3500")["todas"] == ["iphone", "15"]
    assert parse_alerta('ps5 "sem fechar')["todas"] == ["ps5", "sem", "fechar"]


def test_parse_alerta_vazio():
    import pytest

    with pytest.raises(ValueError):
        parse_alerta("-capa max 100")
