"""Testes do /remover (um, vários, tudo)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comandos import executar, parse_alerta  # noqa: E402
from estado import Alertas  # noqa: E402


def com_alertas(tmp_path, n):
    alertas = Alertas(tmp_path, None, ["c1"])
    for i in range(n):
        alertas.adicionar(parse_alerta(f"produto{i}"))
    return alertas


def test_remover_um(tmp_path):
    a = com_alertas(tmp_path, 3)
    assert "removido" in executar("/remover 2", a)[0]
    assert [x["id"] for x in a.alertas] == [1, 3]


def test_remover_varios(tmp_path):
    a = com_alertas(tmp_path, 5)
    txt = executar("/remover 2 3, 4 9", a)[0]
    assert "#2, #3, #4" in txt and "Não achei: #9" in txt
    assert [x["id"] for x in a.alertas] == [1, 5]
    assert "Uso" in executar("/remover 1 abc", a)[0]
    assert len(a.alertas) == 2  # nada apagado com comando inválido


def test_remover_tudo_pede_confirmacao(tmp_path):
    a = com_alertas(tmp_path, 4)
    txt = executar("/remover tudo", a)[0]
    assert "todos os 4 alertas" in txt and "/remover tudo sim" in txt
    assert len(a.alertas) == 4  # ainda não apagou
    assert "4 alerta(s) apagado(s)" in executar("/remover tudo sim", a)[0]
    assert a.alertas == [] and a.mudou
    assert "não tem alertas" in executar("/remover TUDO", a)[0]
