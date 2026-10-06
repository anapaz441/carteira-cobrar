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
    ultimo = progresso.combinar_ultimo(
        pl.DataFrame(
            {
                "codcli": ["1"],
                "ult_data": [date(2026, 10, 2)],
                "ult_hora": ["10:00:00"],
                "ult_usuario": ["A"],
                "ult_resultado": ["X"],
                "ult_texto": ["siac"],
            }
        ),
        pl.DataFrame(
            {
                "codcli": ["1"],
                "cod_usuario": ["B"],
                "criado_em": ["2026-10-03T09:00:00"],
                "cd_negocia": ["11"],
                "resultado": ["EM NEGOCIACAO"],
                "texto": ["app"],
            }
        ),
    )
    recuperado = pl.DataFrame({"codcli": ["1", "3"], "vl_recuperado": [100.0, 999.0]})
    cob = pl.DataFrame(
        {
            "cod_usuario": ["A", "B"],
            "nome": ["Ana", "Bia"],
            "tipo": ["Integral", "Parcial"],
        }
    )
    df = progresso.montar_carteira(cart, situacao, contagem, ultimo, cob, recuperado).sort("codcli")
    assert df["status"].to_list() == [
        progresso.STATUS_META,
        progresso.STATUS_SEM_CONTATO,
        progresso.STATUS_REGULARIZADO,
    ]
    assert df["progresso"].to_list() == [1.0, 0.0, 1.0]
    # recuperado limitado ao que estava na faixa (cliente 3: 999 pago, faixa era 300)
    assert df["recuperado"].to_list() == [100.0, 0.0, 300.0]
    assert df["ult_contato"][0] == "03/10 09:00 · Bia"  # anotação do app é mais nova
    assert df["ult_texto"][0] == "[app] app"
    assert df["cliente"][2] == "C3"  # pegou o nome guardado
    assert df["loja"].to_list() == ["Goiânia", "Recife", "Gama"]
    res = progresso.resumo_por_cobrador(df, cob)
    assert res.filter(pl.col("cod_usuario") == "A")["clientes"][0] == 2


def test_ritmo_esperado():
    assert progresso.ritmo_esperado(date(2026, 10, 31), date(2026, 10, 1)) == 1.0
    assert progresso.ritmo_esperado(date(2026, 10, 1), date(2026, 10, 1)) == pytest.approx(1 / 31)


def test_formatar_telefones_remove_numero_antigo_sem_9():
    t = progresso.formatar_telefones("6191366969,61991366969,6136131029")
    assert t == "(61) 99136-6969 / (61) 3613-1029"
    assert progresso.formatar_telefones(None) == ""


def test_anotacoes_como_contatos_ignora_so_anotacao():
    notas = pl.DataFrame(
        {
            "codcli": ["1", "1"],
            "cod_usuario": ["A", "A"],
            "criado_em": ["2026-10-03T09:00:00", "2026-10-04T09:00:00"],
            "cd_negocia": ["SO_ANOTACAO", "04"],
            "resultado": [None, "X"],
            "texto": ["a", "b"],
        }
    )
    c = progresso.anotacoes_como_contatos(notas)
    assert c.height == 1 and c["dt_cobran"][0] == date(2026, 10, 4)
