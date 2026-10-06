import polars as pl
import pytest

from domain.distribuicao import distribuir, fatias, resumo_equilibrio


def test_fatias_parcial_tem_um_quarto_a_menos(cobradores):
    f = fatias(cobradores)
    assert sum(f.values()) == pytest.approx(1.0)
    assert f["D"] == pytest.approx(f["A"] * 0.75)


def test_todo_cliente_recebe_um_cobrador(clientes, cobradores):
    d = distribuir(clientes, cobradores)
    assert d.height == clientes.height
    assert d["cod_usuario"].null_count() == 0
    assert set(d["codcli"]) == set(clientes["codcli"])


def test_quantidade_e_valor_proporcionais(clientes, cobradores):
    d = distribuir(clientes, cobradores)
    r = resumo_equilibrio(d, cobradores)
    for row in r.iter_rows(named=True):
        # no máximo 2 p.p. de diferença da fatia justa, em quantidade e em valor 16–60d
        assert abs(row["pct_clientes"] - row["fatia"]) < 0.02, row
        assert abs(row["pct_valor"] - row["fatia"]) < 0.02, row


def test_lojas_espalhadas(clientes, cobradores):
    d = distribuir(clientes, cobradores)
    por_loja = d.group_by("loja_principal", "cod_usuario").len()
    for loja in d["loja_principal"].unique():
        qtd = por_loja.filter(pl.col("loja_principal") == loja)["len"]
        n_loja = d.filter(pl.col("loja_principal") == loja).height
        if n_loja >= 6:  # loja com cliente para todos → ninguém fica de fora
            assert qtd.len() == 6
            assert qtd.max() - qtd.min() <= 2


def test_novos_nao_mexem_na_carteira_atual(clientes, cobradores):
    antigos, novos = clientes.head(120), clientes.tail(31)
    base = distribuir(antigos, cobradores)
    extra = distribuir(novos, cobradores, carteira_atual=base)
    assert extra.height == 31
    total = pl.concat(
        [
            base.select("codcli", "cod_usuario", "vl_faixa"),
            extra.select("codcli", "cod_usuario", "vl_faixa"),
        ]
    )
    r = resumo_equilibrio(total, cobradores)
    for row in r.iter_rows(named=True):
        assert abs(row["pct_clientes"] - row["fatia"]) < 0.04, row


def test_sem_cobrador_da_erro(clientes):
    with pytest.raises(ValueError):
        distribuir(clientes, pl.DataFrame(schema={"cod_usuario": pl.Utf8, "tipo": pl.Utf8}))
