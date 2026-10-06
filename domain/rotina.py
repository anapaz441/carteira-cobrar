"""Rotina do dia: quais clientes o cobrador deve trabalhar hoje (função pura)."""

from datetime import date

import polars as pl

from domain.progresso import STATUS_REGULARIZADO


def selecionar_rotina(
    carteira_cobrador: pl.DataFrame, contatados_hoje: set[str], tamanho: int
) -> list[str]:
    """Escolhe até `tamanho` clientes, nesta ordem:
    0. quem NÃO tem acordo ativo em dia vem antes;
    1. sem nenhum contato no ciclo;
    2. menos contatos;
    3. último contato mais antigo (quem está há mais tempo sem ligação);
    4. loja mais crítica; 5. maior débito na faixa.
    Ficam de fora: regularizados e quem já teve contato hoje.
    """
    if "acordo_em_dia" not in carteira_cobrador.columns:
        carteira_cobrador = carteira_cobrador.with_columns(pl.lit(False).alias("acordo_em_dia"))
    candidatos = carteira_cobrador.filter(
        (pl.col("status") != STATUS_REGULARIZADO) & ~pl.col("codcli").is_in(list(contatados_hoje))
    )
    # Cliente com acordo ativo e em dia vai para o fim da fila (já está pagando)
    ordenado = candidatos.sort(
        ["acordo_em_dia", "contatos", "ult_quando", "prioridade", "vl_faixa"],
        descending=[False, False, False, False, True],
        nulls_last=False,
    )
    return ordenado["codcli"].head(tamanho).to_list()


def contatados_no_dia(contatos: pl.DataFrame, dia: date) -> set[str]:
    """Clientes com contato (SIAC ou app) no dia informado."""
    if contatos.is_empty():
        return set()
    return set(contatos.filter(pl.col("dt_cobran") == dia)["codcli"].to_list())
