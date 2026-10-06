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


def formatar_telefones(brutos: str | None) -> str:
    """'61996188828,6196318116' → '(61) 99618-8828 / (61) 9631-8116'.
    Remove o número antigo de 8 dígitos quando a versão com o 9 na frente também existe."""
    if not brutos:
        return ""
    nums = sorted({n for n in brutos.split(",") if n})
    nums = [n for n in nums if not (len(n) == 10 and n[2] in "6789" and f"{n[:2]}9{n[2:]}" in nums)]

    def fmt(n: str) -> str:
        ddd, resto = n[:2], n[2:]
        return f"({ddd}) {resto[:-4]}-{resto[-4:]}"

    # celulares primeiro
    nums.sort(key=lambda n: (len(n) != 11, n))
    return " / ".join(fmt(n) for n in nums)


def anotacoes_como_contatos(notas: pl.DataFrame) -> pl.DataFrame:
    """Anotações do app que foram contato (não "só anotação") no formato das ligações do SIAC."""
    vazio = pl.DataFrame(
        schema={
            "codcli": pl.Utf8,
            "dt_cobran": pl.Date,
            "cd_usuario": pl.Utf8,
            "cd_negocia": pl.Utf8,
        }
    )
    if notas.is_empty():
        return vazio
    return notas.filter(pl.col("cd_negocia") != config.SO_ANOTACAO).select(
        "codcli",
        pl.col("criado_em").str.slice(0, 10).str.to_date().alias("dt_cobran"),
        "cd_usuario"
        if "cd_usuario" in notas.columns
        else pl.col("cod_usuario").alias("cd_usuario"),
        "cd_negocia",
    )


def combinar_ultimo(siac: pl.DataFrame, notas: pl.DataFrame) -> pl.DataFrame:
    """Último contato de cada cliente, olhando SIAC e anotações do app (o mais recente vence)."""
    cols = {
        "codcli": pl.Utf8,
        "ult_quando": pl.Datetime,
        "ult_usuario": pl.Utf8,
        "ult_resultado": pl.Utf8,
        "ult_texto": pl.Utf8,
    }
    partes = []
    if not siac.is_empty():
        partes.append(
            siac.select(
                "codcli",
                (
                    pl.col("ult_data").cast(pl.Utf8)
                    + "T"
                    + pl.col("ult_hora").fill_null("00:00:00").str.slice(0, 8)
                )
                .str.to_datetime(strict=False)
                .alias("ult_quando"),
                pl.col("ult_usuario").cast(pl.Utf8),
                pl.col("ult_resultado").cast(pl.Utf8),
                pl.col("ult_texto").cast(pl.Utf8),
            )
        )
    if not notas.is_empty():
        partes.append(
            notas.sort("criado_em", descending=True)
            .unique("codcli", keep="first")
            .select(
                "codcli",
                pl.col("criado_em").str.to_datetime(strict=False).alias("ult_quando"),
                pl.col("cod_usuario").alias("ult_usuario"),
                pl.col("resultado").fill_null("ANOTAÇÃO").alias("ult_resultado"),
                (pl.lit("[app] ") + pl.col("texto")).alias("ult_texto"),
            )
        )
    if not partes:
        return pl.DataFrame(schema=cols)
    todos = pl.concat([p.cast(cols) for p in partes])
    return todos.sort("ult_quando", descending=True, nulls_last=True).unique("codcli", keep="first")


def montar_carteira(
    carteira: pl.DataFrame,
    situacao: pl.DataFrame,
    contagem: pl.DataFrame,
    ultimo: pl.DataFrame,
    cobradores: pl.DataFrame,
    recuperado: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Tabela final, uma linha por cliente da carteira, pronta para a tela.

    ultimo:     saída de combinar_ultimo (codcli, ult_quando, ult_usuario, ...)
    recuperado: codcli, vl_recuperado (pago dos títulos que estavam na faixa)
    """
    nomes = dict(cobradores.select("cod_usuario", "nome").iter_rows())
    if recuperado is None or recuperado.is_empty():
        recuperado = pl.DataFrame(schema={"codcli": pl.Utf8, "vl_recuperado": pl.Float64})
    if "telefones" not in situacao.columns:
        situacao = situacao.with_columns(pl.lit(None, dtype=pl.Utf8).alias("telefones"))

    df = (
        carteira.join(situacao, on="codcli", how="left", suffix="_atual")
        .join(contagem, on="codcli", how="left")
        .join(ultimo, on="codcli", how="left")
        .join(recuperado.select("codcli", "vl_recuperado"), on="codcli", how="left")
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
            pl.col("vl_recuperado").fill_null(0.0).cast(pl.Float64),
        )
    )
    # Todos os telefones; se o cliente saiu do SIAC "em aberto", usa os guardados
    reserva = pl.concat_str(
        [pl.col("whatsapp").fill_null(""), pl.col("telefone").fill_null("")], separator=","
    ).str.replace_all(r"[^0-9,]", "")
    df = df.with_columns(
        pl.col("telefones")
        .fill_null(reserva)
        .map_elements(formatar_telefones, return_dtype=pl.Utf8)
        .alias("telefones")
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
        # Recuperado = pago dos títulos que estavam na faixa 16–60d quando o cliente entrou
        pl.col("vl_recuperado").clip(upper_bound=pl.col("vl_faixa_ini")).alias("recuperado"),
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
        (pl.col("codcli") + " · " + pl.col("cliente").fill_null("")).alias("cliente_rotulo"),
    )
    return df.with_columns(
        pl.when(pl.col("ult_quando").is_not_null())
        .then(
            pl.col("ult_quando").dt.strftime("%d/%m %H:%M")
            + " · "
            + pl.col("ult_quem").fill_null("?")
        )
        .otherwise(pl.lit("—"))
        .alias("ult_contato")
    )


def resumo_por_cobrador(df: pl.DataFrame, cobradores: pl.DataFrame) -> pl.DataFrame:
    agg = df.group_by("cod_usuario").agg(
        pl.len().alias("clientes"),
        pl.col("vl_faixa_ini").sum().alias("vl_faixa_ini"),
        pl.col("vl_vencido_ini").sum().alias("vl_vencido_ini"),
        pl.col("vl_vencido").sum().alias("vl_vencido_atual"),
        pl.col("vl_faixa").sum().alias("vl_faixa_atual"),
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
            (pl.col("recuperado") / pl.col("vl_faixa_ini")).fill_nan(0).alias("pct_recuperado")
        )
        .sort("tipo", "nome")
    )


def resumo_por_loja(df: pl.DataFrame) -> pl.DataFrame:
    return (
        df.group_by("loja_principal", "loja")
        .agg(
            pl.len().alias("clientes"),
            pl.col("vl_faixa_ini").sum().alias("vl_faixa_ini"),
            pl.col("vl_faixa").sum().alias("vl_faixa_atual"),
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
