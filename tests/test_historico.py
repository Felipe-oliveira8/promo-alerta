"""Testes do /preco (histórico) e das melhorias de preço/normalização."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import historico  # noqa: E402
from comandos import executar, parse_alerta, separar_periodo  # noqa: E402
from estado import Alertas  # noqa: E402
from filtro import casa, preco_oferta  # noqa: E402
from fontes import Oferta  # noqa: E402

AGORA = datetime.now(timezone.utc)


def post_html(canal, n, texto, dias_atras):
    d = (AGORA - timedelta(days=dias_atras)).isoformat()
    return (f'<div class="tgme_widget_message" data-post="{canal}/{n}">'
            f'<div class="tgme_widget_message_text">{texto}</div>'
            f'<time datetime="{d}"></time></div>')


# --- melhorias de filtro ------------------------------------------------------
def test_preco_sem_ponto_de_milhar():
    assert preco_oferta("Placa RTX 5060 8GB R$ 2170,00 Mercado Livre") == 2170.0
    assert preco_oferta("de R$ 3.999 por R$ 2.999 ou 12x de R$ 299,90") == 2999.0
    assert preco_oferta("R$ 2.899 + cupom de R$ 100 OFF") == 2899.0
    assert preco_oferta("Frete grátis acima de R$ 79") is None


def test_um_alerta_pega_todas_as_grafias():
    a = parse_alerta('"5060 ti" 16gb|16g -"pc gamer" -notebook')
    for t in ["RTX 5060 Ti 16GB", "RTX5060Ti 16G", "RTX5060 Ti 16 GB", "RTX 5060-Ti (16GB)",
              "GeForce RTX 5060TI 16GB"]:
        assert casa(a, t)[0], t
    for t in ["RTX 5060 Ti 8GB", "RTX 5060 16GB RAM notebook", "PC Gamer RTX 5060 Ti 16GB",
              "RTX 5070 Ti 16GB"]:
        assert not casa(a, t)[0], t


def test_max_usa_preco_real_e_nao_parcela():
    a = parse_alerta('"5060 ti" max 3000')
    assert not casa(a, "RTX 5060 Ti R$ 3.499 ou 12x de R$ 291,58")[0]
    assert casa(a, "RTX 5060 Ti por R$ 2899,90")[0]


# --- período ------------------------------------------------------------------
def test_periodos():
    assert historico.parse_periodo("3m") == 90
    assert historico.parse_periodo("6meses") == 180
    assert historico.parse_periodo("1a") == 365
    assert historico.parse_periodo("1ano") == 365
    assert historico.parse_periodo("30d") == 30
    assert historico.parse_periodo("16gb") is None
    assert separar_periodo("1 6m") == ("1", 180)
    assert separar_periodo('"5060 ti" 16gb 1 ano') == ('"5060 ti" 16gb', 365)
    assert separar_periodo("2") == ("2", 90)
    assert historico.descrever_periodo(180) == "6 meses"
    assert historico.descrever_periodo(365) == "1 ano"


def test_termo_de_busca():
    assert historico.termo_de_busca(parse_alerta('"5060 ti" 16gb|16g')) == "5060"
    assert historico.termo_de_busca(parse_alerta('"air fryer" mondial')) == "air fryer"


# --- busca paginada -------------------------------------------------------------
class SessaoFalsa:
    """Simula t.me/s/<canal>?q=...&before=N com 20 resultados por página."""

    def __init__(self, posts):
        self.posts = sorted(posts, key=lambda p: p[0])  # (num, texto, dias_atras)
        self.chamadas = []

    def get(self, url, params, headers, timeout):
        self.chamadas.append(dict(params))
        antes = params.get("before", 10**9)
        pagina = [p for p in self.posts if p[0] < antes][-20:]

        class R:
            text = "".join(post_html("canal", n, t, d) for n, t, d in pagina)

            def raise_for_status(self):
                pass

        return R()


def test_busca_para_quando_passa_do_periodo(monkeypatch):
    monkeypatch.setattr(historico, "PAUSA", 0)
    # 100 posts, um por dia (post 100 = hoje, post 1 = 99 dias atrás)
    posts = [(n, f"RTX 5060 Ti 16GB R$ {3000 + n},00", 100 - n) for n in range(1, 101)]
    s = SessaoFalsa(posts)
    desde = AGORA - timedelta(days=30, hours=1)
    achadas = historico.buscar_no_canal("canal", "5060", desde, sessao=s)
    assert len(achadas) == 31                     # só o período pedido
    assert len(s.chamadas) == 2                   # parou na 2ª página (já passou de 30 dias)
    assert s.chamadas[1]["before"] == 81          # paginou para trás


# --- estatística e relatório ---------------------------------------------------
def oferta(n, texto, dias_atras, canal="c1"):
    return Oferta(canal=canal, num=n, texto=texto, link=f"https://t.me/{canal}/{n}",
                  data=(AGORA - timedelta(days=dias_atras)).isoformat())


def test_consultar_calcula_e_filtra(monkeypatch):
    monkeypatch.setattr(historico, "PAUSA", 0)
    base = {
        "c1": [
            oferta(1, "RTX 5060 Ti 16GB R$ 3.000", 10),
            oferta(2, "RTX 5060 Ti 16GB R$ 3.200", 40),
            oferta(3, "RTX 5060 Ti 16GB R$ 2.800", 70),
            oferta(4, "RTX 5060 Ti 8GB R$ 2.300", 5),          # 8GB → fora
            oferta(5, "PC Gamer RTX 5060 Ti 16GB R$ 6.999", 5),  # PC → fora
            oferta(6, "RTX 5060 Ti 16GB R$ 3.100", 200),        # fora do período
            oferta(7, "RTX 5060 Ti 16GB só R$ 99 de entrada", 3),  # valor fora da curva
        ],
        "c2": [
            oferta(8, "RTX5060Ti 16G por R$ 3.400", 20, canal="c2"),
            oferta(9, "RTX 5060 Ti 16GB R$ 3.000", 10, canal="c2"),  # repetida do c1
        ],
    }
    alerta = parse_alerta('"5060 ti" 16gb|16g -"pc gamer" max 2500')  # max é ignorado aqui
    txt = historico.consultar(alerta, 90, ["c1", "c2"], buscar=lambda c, q, d: base[c])
    assert "4 ofertas" in txt                          # 3000, 3200, 2800, 3400
    assert "Valor justo (mediana): R$ 3.100" in txt
    assert "Mínimo: R$ 2.800" in txt
    assert "Máximo: R$ 3.400" in txt
    assert "Média: R$ 3.100" in txt
    assert "Últimos 3 meses" in txt
    assert "Mediana por mês" in txt


def test_consultar_sem_resultado_e_canal_com_erro(monkeypatch):
    monkeypatch.setattr(historico, "PAUSA", 0)

    def buscar(c, q, d):
        if c == "ruim":
            raise RuntimeError("404")
        return []

    txt = historico.consultar(parse_alerta("ps5"), 30, ["bom", "ruim"], buscar=buscar)
    assert "Não encontrei ofertas" in txt and "@ruim" in txt


def test_comando_preco(tmp_path):
    alertas = Alertas(tmp_path, None, ["c1"])
    alertas.adicionar(parse_alerta('"5060 ti" 16gb'))
    chamadas = []

    def consultar(alerta, dias):
        chamadas.append((alerta["todas"], dias))
        return "ok"

    assert executar("/preco 1 6m", alertas, consultar)[0] == "ok"
    assert executar('/preco "air fryer" 1a', alertas, consultar)[0] == "ok"
    assert executar("/preco 1", alertas, consultar)[0] == "ok"
    assert chamadas == [(["5060 ti", "16gb"], 180), (["air fryer"], 365), (["5060 ti", "16gb"], 90)]
    assert "Não achei o alerta #7" in executar("/preco 7 3m", alertas, consultar)[0]
    assert "Uso" in executar("/preco", alertas, consultar)[0]
