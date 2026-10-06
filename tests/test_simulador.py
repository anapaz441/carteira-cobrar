"""Confere o simulador com um acordo REAL do SIAC (loja 06, acordo 000507, 06/10/2026):
principal 3.491,02 · negociado 4.500,00 · juros gravado 3,27831577% · multa 3%."""

from datetime import date

import pytest

from domain import simulador as sim

TITULOS = [
    sim.Titulo("a", "1", date(2026, 1, 18), 700.02, 12, 3),
    sim.Titulo("b", "2", date(2026, 1, 24), 287.96, 12, 3),
    sim.Titulo("c", "3", date(2026, 1, 25), 286.77, 12, 3),
    sim.Titulo("d", "4", date(2026, 2, 6), 241.48, 12, 3),
    sim.Titulo("e", "5", date(2026, 2, 8), 287.98, 12, 3),
    sim.Titulo("f", "6", date(2026, 2, 9), 286.77, 12, 3),
    sim.Titulo("g", "7", date(2026, 2, 17), 700.02, 12, 3),
    sim.Titulo("h", "8", date(2026, 3, 19), 700.02, 12, 3),
]
DATA = date(2026, 10, 6)


def test_juros_e_multa_iguais_ao_siac_com_o_percentual_gravado():
    linhas = sim.calcular_titulos(TITULOS, DATA, pc_juros=3.27831577, pc_multa=3)
    # valores gravados em acor_lan pelo SIAC
    assert [x.juros for x in linhas] == [199.66, 80.24, 79.60, 63.86, 75.53, 74.90, 176.71, 153.76]
    assert [x.multa for x in linhas] == [21.00, 8.64, 8.60, 7.24, 8.64, 8.60, 21.00, 21.00]
    principal, _, _, total = sim.totais(linhas)
    assert principal == 3491.02
    assert total == 4500.00


def test_valor_negociado_acha_o_percentual_de_juros():
    pc, total = sim.juros_para_valor(TITULOS, DATA, 4500.00, 3)
    assert total == 4500.00
    assert pc == pytest.approx(3.2783, abs=0.001)
    assert sim.situacao_prevista(pc, 3)[0] == "N"  # abaixo de 11,80% → não autorizado
    assert sim.situacao_prevista(12, 3)[0] == "A"


def test_valor_impossivel_abaixo_do_principal_mais_multa():
    pc, _ = sim.juros_para_valor(TITULOS, DATA, 3500.00, 3)
    assert pc is None


def test_parcelamento_igual_ao_siac():
    # acordo real quinzenal: 3.210,00 em parcelas de 600 → 6 parcelas, última 210
    p = sim.parcelar(3210.00, "V", 600, "Q", date(2026, 10, 1), date(2026, 9, 30))
    assert p.quantidade == 6
    assert [v for _, _, v in p.parcelas] == [600, 600, 600, 600, 600, 210]
    assert [d for _, d, _ in p.parcelas][:3] == [
        date(2026, 10, 1),
        date(2026, 10, 15),
        date(2026, 10, 29),
    ]
    # mensal dia 15: 4.398 em 800 → 6 parcelas, última 398
    m = sim.parcelar(4398.00, "V", 800, "M", date(2026, 9, 15), date(2026, 9, 10))
    assert [v for _, _, v in m.parcelas][-1] == 398.00
    assert m.parcelas[1][1] == date(2026, 10, 15)
    # por quantidade
    q = sim.parcelar(1000.00, "Q", 3, "S", date(2026, 10, 9), date(2026, 10, 6))
    assert [v for _, _, v in q.parcelas] == [333.34, 333.34, 333.32]


def test_primeiro_vencimento():
    # 06/10/2026 é terça; sexta ('06') → 09/10
    assert sim.primeiro_vencimento(date(2026, 10, 6), "S", "06") == date(2026, 10, 9)
    # segunda ('02') → próxima segunda 12/10
    assert sim.primeiro_vencimento(date(2026, 10, 6), "S", "02") == date(2026, 10, 12)
    # mensal dia 5 já passou → 05/11
    assert sim.primeiro_vencimento(date(2026, 10, 6), "M", "5") == date(2026, 11, 5)
