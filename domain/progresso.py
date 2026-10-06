"""Acompanhamento da carteira: junta a carteira salva + débito atual + ligações do SIAC.

Funções puras (entram tabelas, saem tabelas). Sem Streamlit e sem SQL.
"""

import calendar
from datetime import date

import polars as pl

import config

STATUS_REGULARIZADO = "Regularizado"
STATUS_META = "Meta atingida"
STATUS_ANDAMENTO = "Em andamento"
STATUS_SEM_CONTATO = "Sem contato"
ORDEM_STATUS = [STATUS_SEM_CONTATO, STATUS_ANDAMENTO, STATUS_META, STATUS_REGULARIZADO]


def contar_contatos(contatos: pl.DataFrame, carteira: pl.DataFrame) -> pl.DataFrame:
    """Contatos por cliente no ciclo: total, efetivos e quantos foram do cobrador dono.

    contatos: codcli, dt_cobran, cd_usuario, cd_negocia (uma linha por ligação)
    carteira: codcli, cod_usuario
    """
    if contatos.is_empty():
        return pl.DataFrame(
            schema={
                "codcli": pl.Utf8,
                "contatos": pl.Int64,
                "efetivos": pl.Int64,
                "contatos_dono": pl.Int64,
            }
        )
    c = contatos.join(carteira.select("codcli", "cod_usuario"), on="codcli", how="inner")
    efetivo = ~pl.col("cd_negocia").is_in(list(config.NEGOCIACAO_NAO_EFETIVA))
    do_dono = pl.col("cd_usuario") == pl.col("cod_usuario")
    if config.UM_CONTATO_POR_DIA:
        # 1 contato por dia, no máximo
        agg = [
            pl.col("dt_cobran").n_unique().alias("contatos"),
            pl.col("dt_cobran").filter(efetivo).n_unique().alias("efetivos"),
            pl.col("dt_cobran").filter(do_dono).n_unique().alias("contatos_dono"),
        ]
    else:
        agg = [
            pl.len().alias("contatos"),
            efetivo.sum().alias("efetivos"),
            do_dono.sum().alias("contatos_dono"),
        ]
    return c.group_by("codcli").agg(agg).with_columns(pl.all().exclude("codcli").cast(pl.Int64))


def montar_carteira(
    carteira: pl.DataFrame,
    situacao: pl.DataFrame,
    contagem: pl.DataFrame,
    ultimo: pl.DataFrame,
    cobradores: pl.DataFrame,
) -> pl.DataFrame:
    """Tabela final, uma linha por cliente da carteira, pronta para a tela."""
    nomes = dict(cobradores.select("cod_usuario", "nome").iter_rows())

    df = (
        carteira.join(situacao, on="codcli", how="left", suffix="_atual")
        .join(contagem, on="codcli", how="left")
        .join(ultimo, on="codcli", how="left")
        .with_columns(
            pl.col("vl_vencido").fill_null(0.0),
            pl.col("vl_faixa").fill_null(0.0),
            pl.col("qt_titulos").fill_null(0),
            pl.col("contatos").fill_null(0),
            pl.col("efetivos").fill_null(0),
            pl.col("contatos_dono").fill_null(0),
            # Dados cadastrais: usa o atual do SIAC; se o cliente já pagou tudo,
            # usa o que foi guardado quando a carteira foi gerada.
            *[
                pl.col(c).fill_null(pl.col(f"{c}_ini")).alias(c)
                for c in ("cliente", "fantasia", "telefone", "whatsapp")
            ],
        )
    )
    regularizado = pl.col("vl_vencido") <= 0.009
    df = df.with_columns(
        pl.when(regularizado)
        .then(pl.lit(STATUS_REGULARIZADO))
        .when(pl.col("contatos") >= config.META_CONTATOS)
        .then(pl.lit(STATUS_META))
        .when(pl.col("contatos") == 0)
        .then(pl.lit(STATUS_SEM_CONTATO))
        .otherwise(pl.lit(STATUS_ANDAMENTO))
        .alias("status"),
        # Regularizado conta como 100% (não precisa mais ligar)
        pl.when(regularizado)
        .then(1.0)
        .otherwise((pl.col("contatos") / config.META_CONTATOS).clip(0, 1))
        .alias("progresso"),
        (pl.col("vl_vencido_ini") - pl.col("vl_vencido")).clip(lower_bound=0).alias("recuperado"),
        pl.col("loja_principal")
        .replace_strict(config.LOJAS_PRIORIDADE, default="Outra", return_dtype=pl.Utf8)
        .alias("loja"),
        pl.col("cod_usuario")
        .replace_strict(nomes, default=None, return_dtype=pl.Utf8)
        .fill_null(pl.col("cod_usuario"))
        .alias("cobrador"),
        pl.col("ult_usuario")
        .replace_strict(nomes, default=None, return_dtype=pl.Utf8)
        .fill_null(pl.col("ult_usuario"))
        .alias("ult_quem"),
    )
    return df


def resumo_por_cobrador(df: pl.DataFrame, cobradores: pl.DataFrame) -> pl.DataFrame:
    agg = df.group_by("cod_usuario").agg(
        pl.len().alias("clientes"),
        pl.col("vl_faixa_ini").sum().alias("vl_faixa_ini"),
        pl.col("vl_vencido_ini").sum().alias("vl_vencido_ini"),
        pl.col("vl_vencido").sum().alias("vl_vencido_atual"),
        pl.col("recuperado").sum().alias("recuperado"),
        pl.col("contatos").sum().alias("contatos"),
        pl.col("efetivos").sum().alias("efetivos"),
        pl.col("progresso").mean().alias("progresso"),
        (pl.col("status") == STATUS_SEM_CONTATO).sum().alias("sem_contato"),
        (pl.col("status") == STATUS_META).sum().alias("meta_atingida"),
        (pl.col("status") == STATUS_REGULARIZADO).sum().alias("regularizados"),
    )
    return (
        cobradores.select("cod_usuario", "nome", "tipo")
        .join(agg, on="cod_usuario", how="inner")
        .with_columns(
            (pl.col("recuperado") / pl.col("vl_vencido_ini")).fill_nan(0).alias("pct_recuperado")
        )
        .sort("tipo", "nome")
    )


def resumo_por_loja(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.group_by("loja_principal", "loja")
        .agg(
            pl.len().alias("clientes"),
            pl.col("vl_vencido_ini").sum().alias("vl_vencido_ini"),
            pl.col("vl_vencido").sum().alias("vl_vencido_atual"),
            pl.col("recuperado").sum().alias("recuperado"),
            pl.col("progresso").mean().alias("progresso"),
            (pl.col("status") == STATUS_SEM_CONTATO).sum().alias("sem_contato"),
        )
        .with_columns(
            pl.col("loja_principal")
            .replace_strict(config.PRIORIDADE_LOJA, default=99, return_dtype=pl.Int32)
            .alias("prioridade")
        )
        .sort("prioridade")
    )


def ritmo_esperado(hoje: date, inicio: date) -> float:
    """Fração da meta que já deveria ter sido feita hoje (0 a 1), pelo calendário do mês."""
    fim = date(inicio.year, inicio.month, calendar.monthrange(inicio.year, inicio.month)[1])
    total = (fim - inicio).days + 1
    passados = min(max((hoje - inicio).days + 1, 0), total)
    return passados / total if total else 1.0
