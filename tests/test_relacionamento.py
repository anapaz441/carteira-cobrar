import random
from datetime import date

import polars as pl

from domain import relacionamento as rel

NOMES = {
    "8177": "Pedro",
    "3522": "Cleuciane",
    "8526": "Paulo",
    "2281": "Gleyce",
    "4366": "Samuel",
    "4369": "Gabriel",
}


def test_quem_fechou_pega_a_assinatura_no_fim():
    assert rel.quem_fechou("FIRMEI COM ALINE, SEM MAIS A VENCER", "GABRIEL", NOMES) == "4369"
    assert rel.quem_fechou("FIRMEI COM IVANIZIA", "CIENTE DO SERASA PEDRO", NOMES) == "8177"
    assert rel.quem_fechou("FIRMEI COM PEDRO, SEM MAIS A VENCER", "CLEUCIANE", NOMES) == "3522"
    assert rel.quem_fechou("FIRMEI COM HERLEN SEM MAIS A VENCER. CARLA", "", NOMES) is None
    assert rel.quem_fechou("TENDO + 3 BOL", "A VENCER. CLEUCIANE", NOMES) == "3522"


def _cobradores():
    return pl.DataFrame(
        {
            "cod_usuario": list(NOMES),
            "nome": list(NOMES.values()),
            "tipo": ["Integral", "Integral", "Integral", "Parcial", "Parcial", "Parcial"],
        }
    )


def test_relacionamento_com_teto(clientes):
    # Pedro (8177) falou com quase todo mundo; outros com alguns
    rnd = random.Random(3)
    linhas = []
    for c in clientes["codcli"]:
        linhas.append(
            {
                "codcli": c,
                "cd_usuario": "8177",
                "dias_contato": rnd.randint(1, 9),
                "ult_contato": date(2026, 10, 5),
            }
        )
        if rnd.random() < 0.5:
            linhas.append(
                {
                    "codcli": c,
                    "cd_usuario": rnd.choice(["2281", "4366", "3522"]),
                    "dias_contato": rnd.randint(1, 9),
                    "ult_contato": date(2026, 10, 4),
                }
            )
    contatos = pl.DataFrame(linhas)
    acordo = {clientes["codcli"][0]: "4369"}  # Gabriel fechou acordo com o 1º cliente

    d = rel.distribuir_por_relacionamento(clientes, _cobradores(), contatos, acordo)
    assert d.height == clientes.height
    assert d["codcli"].n_unique() == clientes.height
    por = dict(d.group_by("cod_usuario").len().iter_rows())
    # ninguém passa do teto (integral ~29, parcial ~22)
    assert por["8177"] <= 29
    print("POR", por)
    assert all(v <= 29 for v in por.values())
    # Paulo, sem relacionamento, recebe a sobra
    assert por.get("8526", 0) > 0
    # acordo respeitado
    primeiro = d.filter(pl.col("codcli") == clientes["codcli"][0]).row(0, named=True)
    assert primeiro["cod_usuario"] == "4369" and primeiro["motivo"] == rel.MOTIVO_ACORDO
    # quem ficou com o Pedro foi por relacionamento
    assert set(d.filter(pl.col("cod_usuario") == "8177")["motivo"]) == {rel.MOTIVO_CONTATO}


def test_assinatura_composta_pedro_paulo():
    t = "FIRMEI COM ALINE BOSL ATE 21/06 CIENTE DO SERASA PEDRO PAULO"
    assert rel.quem_fechou(t, "", NOMES) == "8177"
    assert rel.quem_fechou("S/+ BOL A VENCE R. PAULO", "", NOMES) == "8526"
