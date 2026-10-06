from datetime import date

import polars as pl
import pytest

from domain import progresso


def _carteira():
    return pl.DataFrame(
        {
            "codcli": ["1", "2", "3"],
            "cod_usuario": ["A", "A", "B"],
            "loja_principal": ["08", "10", "05"],
            "prioridade": [1, 7, 4],
            "vl_vencido_ini": [1000.0, 500.0, 300.0],
            "vl_faixa_ini": [800.0, 500.0, 300.0],
            "cliente_ini": ["C1", "C2", "C3"],
            "fantasia_ini": [None, None, None],
            "telefone_ini": [None, None, None],
            "whatsapp_ini": [None, None, None],
        }
    )


def test_contar_contatos_um_por_dia_e_efetivos():
    contatos = pl.DataFrame(
        {
            "codcli": ["1", "1", "1", "1", "2"],
            "dt_cobran": [
                date(2026, 10, 1),
                date(2026, 10, 1),
                date(2026, 10, 2),
                date(2026, 10, 3),
                date(2026, 10, 2),
            ],
            "cd_usuario": ["A", "A", "X", "A", "A"],
            "cd_negocia": ["04", "11", "04", "04", "12"],
        }
    )
    r = progresso.contar_contatos(contatos, _carteira()).sort("codcli")
    c1 = r.row(0, named=True)
    assert c1["contatos"] == 3  # 3 dias diferentes
    assert c1["efetivos"] == 1  # só o "11 - em negociação" do dia 1
    assert c1["contatos_dono"] == 2  # dias 1 e 3 foram do cobrador A


def test_montar_carteira_status():
    cart = _carteira()
    situacao = pl.DataFrame(
        {  # cliente 3 pagou tudo (não aparece)
            "codcli": ["1", "2"],
            "vl_vencido": [900.0, 500.0],
            "vl_faixa": [700.0, 500.0],
            "qt_titulos": [3, 1],
            "cliente": ["C1", "C2"],
            "fantasia": [None, None],
            "telefone": [None, None],
            "whatsapp": [None, None],
            "loja_principal": ["08", "10"],
        }
    )
    contagem = pl.DataFrame(
        {"codcli": ["1"], "contatos": [6], "efetivos": [2], "contatos_dono": [6]}
    )
    ultimo = pl.DataFrame({"codcli": ["1"], "ult_usuario": ["A"]})
    cob = pl.DataFrame(
        {
            "cod_usuario": ["A", "B"],
            "nome": ["Ana", "Bia"],
            "tipo": ["Integral", "Parcial"],
        }
    )
    df = progresso.montar_carteira(cart, situacao, contagem, ultimo, cob).sort("codcli")
    assert df["status"].to_list() == [
        progresso.STATUS_META,
        progresso.STATUS_SEM_CONTATO,
        progresso.STATUS_REGULARIZADO,
    ]
    assert df["progresso"].to_list() == [1.0, 0.0, 1.0]
    assert df["recuperado"].to_list() == [100.0, 0.0, 300.0]
    assert df["cliente"][2] == "C3"  # pegou o nome guardado
    assert df["loja"].to_list() == ["Goiânia", "Recife", "Gama"]
    res = progresso.resumo_por_cobrador(df, cob)
    assert res.filter(pl.col("cod_usuario") == "A")["clientes"][0] == 2


def test_ritmo_esperado():
    assert progresso.ritmo_esperado(date(2026, 10, 31), date(2026, 10, 1)) == 1.0
    assert progresso.ritmo_esperado(date(2026, 10, 1), date(2026, 10, 1)) == pytest.approx(1 / 31)
