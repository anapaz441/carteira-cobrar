"""Orquestra: busca os dados (camada data/) e aplica as regras (distribuicao/progresso).

As telas chamam só este módulo — nunca SQL direto.
"""

from datetime import date

import polars as pl

import config
from data import carteira_store as store
from data.queries import acordos as q_acordos
from data.queries import contatos as q_contatos
from data.queries import titulos as q_titulos
from domain import distribuicao, progresso
from domain import relacionamento as rel_mod
from domain import rotina as rotina_mod


def mes_atual(hoje: date | None = None) -> str:
    hoje = hoje or date.today()
    return f"{hoje.year:04d}-{hoje.month:02d}"


def cobradores(somente_ativos: bool = True) -> pl.DataFrame:
    return pl.from_pandas(store.listar_cobradores(somente_ativos=somente_ativos))


def elegiveis() -> pl.DataFrame:
    """Clientes que hoje têm algum título vencido entre 16 e 60 dias."""
    return pl.from_pandas(q_titulos.clientes_elegiveis())


def previa_distribuicao() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Simula a carteira (sem salvar). Devolve (distribuição, conferência por cobrador)."""
    cob = cobradores()
    dist = distribuicao.distribuir(elegiveis(), cob)
    return dist, distribuicao.resumo_equilibrio(dist, cob)


def gerar_carteira(mes: str, inicio: date | None = None, dist: pl.DataFrame | None = None) -> int:
    """Gera e SALVA a carteira do mês (refaz se já existia).
    Se `dist` vier (a prévia que a pessoa conferiu), salva exatamente ela."""
    if dist is None:
        dist, _ = previa_distribuicao()
    inicio = inicio or date(int(mes[:4]), int(mes[5:7]), 1)
    return store.salvar_ciclo(mes, inicio.isoformat(), dist.to_pandas())


def carteira_salva(ciclo_id: int) -> pl.DataFrame:
    return pl.from_pandas(store.carteira_do_ciclo(ciclo_id))


def clientes_novos(ciclo_id: int) -> pl.DataFrame:
    """Elegíveis hoje que ainda NÃO estão na carteira do mês."""
    atuais = carteira_salva(ciclo_id)["codcli"].to_list()
    return elegiveis().filter(~pl.col("codcli").is_in(atuais))


def distribuir_novos(ciclo_id: int) -> int:
    """Encaixa os clientes novos sem mexer em quem já está na carteira."""
    novos = clientes_novos(ciclo_id)
    if novos.is_empty():
        return 0
    atual = carteira_salva(ciclo_id).rename(
        {"vl_faixa_ini": "vl_faixa", "vl_vencido_ini": "vl_vencido"}
    )
    dist = distribuicao.distribuir(novos, cobradores(), carteira_atual=atual)
    store.adicionar_clientes(ciclo_id, dist.to_pandas(), origem="novo")
    return dist.height


_SCHEMA_LIGACOES = {
    "codcli": pl.Utf8,
    "dt_cobran": pl.Date,
    "cd_usuario": pl.Utf8,
    "cd_negocia": pl.Utf8,
}


# ---------------------------------------------------------------------------
# Consultas ao SIAC sempre pelo MESMO conjunto de clientes ("universo" = carteira do
# mês + clientes com acordo ativo). Assim a tela inteira reaproveita o cache: em vez de
# várias consultas pesadas (uma por lista de clientes), o banco é consultado 1 vez.
# ---------------------------------------------------------------------------
def _universo(codigos: tuple[str, ...]) -> tuple[str, ...]:
    base = set(codigos)
    ciclo = store.obter_ciclo(mes_atual())
    if ciclo:
        base |= set(store.carteira_do_ciclo(ciclo["id"])["codcli"].tolist())
    acordos = q_acordos.acordos_ativos()
    if not acordos.empty:
        base |= set(acordos["codcli"].tolist())
    return tuple(sorted(base))


def _filtrar(df: pl.DataFrame, codigos: tuple[str, ...]) -> pl.DataFrame:
    return df if df.is_empty() else df.filter(pl.col("codcli").is_in(list(codigos)))


def _situacao(codigos: tuple[str, ...]) -> pl.DataFrame:
    return _filtrar(pl.from_pandas(q_titulos.situacao_atual(_universo(codigos))), codigos)


def _ultimo_siac(codigos: tuple[str, ...]) -> pl.DataFrame:
    return _filtrar(pl.from_pandas(q_contatos.ultimo_contato(_universo(codigos))), codigos)


def _ligacoes_siac(inicio: date, codigos: tuple[str, ...]) -> pl.DataFrame:
    df = pl.from_pandas(q_contatos.contatos_no_ciclo(inicio, _universo(codigos)))
    if df.is_empty():
        return pl.DataFrame(schema=_SCHEMA_LIGACOES)
    return _filtrar(df.select(list(_SCHEMA_LIGACOES)).cast(_SCHEMA_LIGACOES), codigos)


def _notas(codigos: tuple[str, ...], desde: str | None = None) -> pl.DataFrame:
    notas = store.anotacoes(list(codigos), desde=desde)
    return (
        pl.from_pandas(notas)
        if not notas.empty
        else pl.DataFrame(schema={c: pl.Utf8 for c in notas.columns})
    )


def inicio_do_ciclo(ciclo: dict) -> date:
    """Os contatos contam a partir do DIA 1 do mês da carteira."""
    return date(int(ciclo["mes"][:4]), int(ciclo["mes"][5:7]), 1)


def contatos_do_ciclo(ciclo: dict) -> pl.DataFrame:
    """Todas as ligações do mês da carteira (desde o dia 1): SIAC + contatos do app."""
    cart = carteira_salva(ciclo["id"])
    codigos = tuple(sorted(cart["codcli"].to_list()))
    inicio = inicio_do_ciclo(ciclo)
    siac = _ligacoes_siac(inicio, codigos)
    app = progresso.anotacoes_como_contatos(_notas(codigos, desde=inicio.isoformat()))
    return pl.concat([siac, app.cast(_SCHEMA_LIGACOES)])


def sugestao_novos(ciclo_id: int) -> pl.DataFrame:
    """Clientes novos na faixa (fora da carteira) com o cobrador SUGERIDO pela regra de
    distribuição (equilíbrio de quantidade, valor e loja). Não salva nada."""
    novos = clientes_novos(ciclo_id)
    if novos.is_empty():
        return novos
    atual = carteira_salva(ciclo_id).rename(
        {"vl_faixa_ini": "vl_faixa", "vl_vencido_ini": "vl_vencido"}
    )
    return distribuicao.distribuir(novos, cobradores(), carteira_atual=atual)


def atribuir_novos(ciclo_id: int, escolhidos: pl.DataFrame) -> int:
    """Salva os clientes novos com o cobrador escolhido na tela.
    escolhidos: saída de sugestao_novos, com a coluna cod_usuario possivelmente alterada."""
    if escolhidos.is_empty():
        return 0
    store.adicionar_clientes(ciclo_id, escolhidos.to_pandas(), origem="novo")
    return escolhidos.height


def progresso_diario(ciclo: dict, painel_df: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """% da meta de contatos de cada cobrador, dia a dia, desde o dia 1 do mês."""
    return progresso.progresso_diario(
        contatos_do_ciclo(ciclo),
        painel_df.select("codcli", "cod_usuario", "status"),
        inicio_do_ciclo(ciclo),
        min(date.today(), progresso.fim_do_mes(inicio_do_ciclo(ciclo))),
        cobradores(False),
    )


def painel(ciclo: dict) -> pl.DataFrame:
    """Carteira do ciclo com débito atual, contatos, recuperado e último contato
    — 1 linha por cliente."""
    cart = carteira_salva(ciclo["id"])
    if cart.is_empty():
        return pl.DataFrame()
    codigos = tuple(sorted(cart["codcli"].to_list()))

    situacao = _situacao(codigos)
    if situacao.is_empty():
        situacao = pl.DataFrame(
            schema={
                "codcli": pl.Utf8,
                "vl_vencido": pl.Float64,
                "vl_faixa": pl.Float64,
                "qt_titulos": pl.Int64,
                "dias_atraso_max": pl.Int64,
                "cliente": pl.Utf8,
                "fantasia": pl.Utf8,
                "telefone": pl.Utf8,
                "whatsapp": pl.Utf8,
                "telefones": pl.Utf8,
            }
        )

    # Recuperado: cada cliente é medido a partir do dia em que entrou na carteira
    ref = cart.select("codcli", pl.col("entrou_em").str.slice(0, 10).alias("dt_ref")).sort("codcli")
    recuperado = pl.from_pandas(
        q_titulos.recuperado_na_faixa(tuple(ref["codcli"]), tuple(ref["dt_ref"]))
    )

    contatos = contatos_do_ciclo(ciclo)
    siac_ult = _ultimo_siac(codigos)
    ultimo = progresso.combinar_ultimo(siac_ult, _notas(codigos))

    contagem = progresso.contar_contatos(contatos, cart)
    df = progresso.montar_carteira(cart, situacao, contagem, ultimo, cobradores(False), recuperado)
    acordos = pl.from_pandas(q_acordos.acordos_clientes(codigos))
    return progresso.marcar_acordos(df, acordos)


def historico(codcli: str) -> pl.DataFrame:
    """Histórico do cliente: ligações do SIAC (120 dias) + anotações do app, juntas."""
    siac = pl.from_pandas(q_contatos.historico_cliente(codcli))
    nomes = dict(cobradores(False).select("cod_usuario", "nome").iter_rows()) | config.GESTORES
    partes = []
    if not siac.is_empty():
        partes.append(
            siac.select(
                (
                    pl.col("data").cast(pl.Utf8)
                    + " "
                    + pl.col("hora").cast(pl.Utf8).fill_null("").str.slice(0, 5)
                ).alias("quando"),
                pl.col("cd_usuario").cast(pl.Utf8),
                pl.lit("SIAC").alias("origem"),
                pl.col("resultado").cast(pl.Utf8),
                pl.col("anotacao").cast(pl.Utf8).alias("texto"),
            )
        )
    notas = _notas((codcli,))
    if not notas.is_empty():
        partes.append(
            notas.select(
                pl.col("criado_em").str.replace("T", " ").str.slice(0, 16).alias("quando"),
                pl.col("cod_usuario").alias("cd_usuario"),
                pl.lit("App").alias("origem"),
                pl.col("resultado").fill_null("ANOTAÇÃO"),
                "texto",
            )
        )
    if not partes:
        return pl.DataFrame()
    return (
        pl.concat(partes)
        .with_columns(
            pl.col("cd_usuario")
            .replace_strict(nomes, default=None, return_dtype=pl.Utf8)
            .fill_null(pl.col("cd_usuario"))
            .alias("quem")
        )
        .sort("quando", descending=True)
    )


def registrar_contato(
    codcli: str, cod_usuario: str, tipo: str, canal: str | None, texto: str
) -> None:
    """Registra no app um contato (efetivo / sem retorno) ou uma simples anotação."""
    if tipo == config.SO_ANOTACAO:
        canal, resultado = None, "ANOTAÇÃO"
    elif tipo == config.CONTATO_EFETIVO:
        resultado = f"CONTATO EFETIVO · {canal.upper()}"
    else:
        resultado = f"SEM RETORNO · {canal.upper()}"
    store.salvar_anotacao(codcli, cod_usuario, tipo, canal, resultado, texto)


def clientes_acordo_atrasado(ciclo: dict, cod_usuario: str) -> pl.DataFrame:
    """Clientes dos acordos ATIVOS do cobrador com parcela vencida, no mesmo formato da
    carteira (para o cartão da rotina) — inclusive quem está fora da faixa 16–60 dias.
    Coluna extra `contatado_hoje`."""
    acordos = meus_acordos(cod_usuario, ciclo)
    if acordos.is_empty():
        return pl.DataFrame()
    atr = acordos.filter(pl.col("atrasadas") > 0).unique("codcli", keep="first")
    if atr.is_empty():
        return pl.DataFrame()
    codigos = tuple(sorted(atr["codcli"].to_list()))
    inicio = inicio_do_ciclo(ciclo)

    # débito e telefones atuais
    sit = _situacao(codigos)
    if not sit.is_empty():
        sit = sit.select(
            "codcli",
            "qt_titulos",
            "vl_vencido",
            "vl_faixa",
            "dias_atraso_max",
            "fantasia",
            pl.col("telefones")
            .map_elements(progresso.formatar_telefones, return_dtype=pl.Utf8)
            .alias("telefones"),
        )
    # contatos do mês (SIAC + app)
    lig = pl.concat(
        [
            _ligacoes_siac(inicio, codigos),
            progresso.anotacoes_como_contatos(_notas(codigos, desde=inicio.isoformat())).cast(
                _SCHEMA_LIGACOES
            ),
        ]
    )
    if config.UM_CONTATO_POR_DIA:
        lig_cont = lig.unique(["codcli", "dt_cobran"])
    else:
        lig_cont = lig
    efetivo = ~pl.col("cd_negocia").is_in(list(config.NEGOCIACAO_NAO_EFETIVA))
    cont = lig_cont.group_by("codcli").agg(
        pl.len().alias("contatos"), efetivo.sum().alias("efetivos")
    )
    hoje = set(lig.filter(pl.col("dt_cobran") == date.today())["codcli"].to_list())

    ult = progresso.combinar_ultimo(_ultimo_siac(codigos), _notas(codigos))
    df = atr.drop("ult_contato", "ult_quando", "ult_resultado", strict=False)
    if not sit.is_empty():
        df = df.join(sit, on="codcli", how="left")
    df = df.join(cont, on="codcli", how="left").join(ult, on="codcli", how="left")
    nomes = dict(cobradores(False).select("cod_usuario", "nome").iter_rows()) | config.GESTORES
    for col, tipo in (
        ("qt_titulos", pl.Int64),
        ("vl_vencido", pl.Float64),
        ("vl_faixa", pl.Float64),
        ("dias_atraso_max", pl.Int64),
        ("telefones", pl.Utf8),
        ("fantasia", pl.Utf8),
    ):
        if col not in df.columns:
            df = df.with_columns(pl.lit(None, dtype=tipo).alias(col))
    return df.with_columns(
        pl.col("contatos").fill_null(0).cast(pl.Int64),
        pl.col("efetivos").fill_null(0).cast(pl.Int64),
        pl.col("vl_faixa").fill_null(0.0),
        pl.col("vl_vencido").fill_null(0.0),
        pl.col("qt_titulos").fill_null(0),
        pl.col("cd_loja")
        .replace_strict(config.LOJAS_PRIORIDADE, default=None, return_dtype=pl.Utf8)
        .fill_null(pl.col("cd_loja"))
        .alias("loja"),
        pl.lit(True).alias("acordo_ativo"),
        pl.lit(True).alias("acordo_atrasado"),
        pl.col("situacao_acordo")
        .replace_strict(config.ACORDO_ROTULO, default="Ativo", return_dtype=pl.Utf8)
        .alias("acordo"),
        pl.format("{}/{} pagas", pl.col("pagas"), pl.col("parcelas")).alias("acordo_parcelas"),
        pl.col("codcli").is_in(list(hoje)).alias("contatado_hoje"),
        pl.when(pl.col("ult_quando").is_not_null())
        .then(
            pl.col("ult_quando").dt.strftime("%d/%m %H:%M")
            + " · "
            + pl.col("ult_usuario")
            .replace_strict(nomes, default=None, return_dtype=pl.Utf8)
            .fill_null(pl.col("ult_usuario"))
            .fill_null("?")
        )
        .otherwise(pl.lit("—"))
        .alias("ult_contato"),
    ).sort(["atrasadas", "prox_vcto"], descending=[True, False], nulls_last=True)


def rotina(
    ciclo: dict,
    cod_usuario: str,
    df_cobrador: pl.DataFrame,
    gerar: bool,
    tamanho: int = config.ROTINA_TAMANHO_PADRAO,
    acordos_atrasados: pl.DataFrame | None = None,
) -> list[str]:
    """Rotina de hoje do cobrador. Se `gerar`, monta uma nova e salva.

    Primeiro entram TODOS os clientes dos acordos dele com parcela vencida (que ainda não
    tiveram contato hoje); depois `tamanho` clientes da carteira pela regra normal."""
    hoje = date.today()
    if gerar:
        feitos = rotina_mod.contatados_no_dia(contatos_do_ciclo(ciclo), hoje)
        primeiro: list[str] = []
        if acordos_atrasados is not None and not acordos_atrasados.is_empty():
            primeiro = acordos_atrasados.filter(
                ~pl.col("contatado_hoje") & ~pl.col("codcli").is_in(list(feitos))
            )["codcli"].to_list()
        resto = df_cobrador.filter(~pl.col("codcli").is_in(primeiro))
        lista = primeiro + rotina_mod.selecionar_rotina(resto, feitos, tamanho)
        store.salvar_rotina(cod_usuario, hoje.isoformat(), lista)
        return lista
    return store.rotina_do_dia(cod_usuario, hoje.isoformat())


def contatados_hoje(ciclo: dict) -> set[str]:
    return rotina_mod.contatados_no_dia(contatos_do_ciclo(ciclo), date.today())


# ----------------------------- acordos ------------------------------------
def acordos_com_responsavel() -> pl.DataFrame:
    """Acordos ativos com a coluna `fechado_por` (cobrador que assinou a observação)."""
    nomes = dict(cobradores(False).select("cod_usuario", "nome").iter_rows())
    acordos = pl.from_pandas(q_acordos.acordos_ativos())
    return rel_mod.marcar_quem_fechou(acordos, nomes)


def dono_dos_acordos(acordos: pl.DataFrame, ciclo: dict | None) -> pl.DataFrame:
    """Coluna `responsavel`: UM cobrador por cliente, mesmo com acordo em mais de uma loja.

    1. Cliente na carteira do mês → o cobrador da carteira (manda a carteira).
    2. Fora da carteira → quem fechou o acordo mais recente do cliente (assinatura).
    Assim o cliente nunca aparece para dois cobradores ao mesmo tempo."""
    fechou = (
        acordos.filter(pl.col("fechado_por").is_not_null())
        .sort(["dt_acordo", "sq_acordo"], descending=True)
        .unique("codcli", keep="first")
        .select("codcli", pl.col("fechado_por").alias("_fechou"))
    )
    cart = (
        carteira_salva(ciclo["id"]).select("codcli", pl.col("cod_usuario").alias("_cart"))
        if ciclo
        else pl.DataFrame(schema={"codcli": pl.Utf8, "_cart": pl.Utf8})
    )
    return (
        acordos.join(fechou, on="codcli", how="left")
        .join(cart, on="codcli", how="left")
        .with_columns(pl.coalesce("_cart", "_fechou").alias("responsavel"))
        .drop("_cart", "_fechou")
    )


def meus_acordos(cod_usuario: str, ciclo: dict | None = None) -> pl.DataFrame:
    """Acordos ativos dos clientes que são do cobrador (parcela atrasada primeiro).
    Dono do cliente: ver `dono_dos_acordos` (carteira do mês > quem fechou)."""
    df = acordos_com_responsavel()
    if df.is_empty():
        return df
    if ciclo is None:
        ciclo = store.obter_ciclo(mes_atual())
    meus = dono_dos_acordos(df, ciclo).filter(pl.col("responsavel") == cod_usuario)
    if meus.is_empty():
        return meus

    # Último contato com o cliente (SIAC ou app), de qualquer cobrador
    codigos = tuple(sorted(set(meus["codcli"].to_list())))
    ultimo = progresso.combinar_ultimo(_ultimo_siac(codigos), _notas(codigos))
    nomes = dict(cobradores(False).select("cod_usuario", "nome").iter_rows()) | config.GESTORES
    ultimo = ultimo.with_columns(
        pl.when(pl.col("ult_quando").is_not_null())
        .then(
            pl.col("ult_quando").dt.strftime("%d/%m %H:%M")
            + " · "
            + pl.col("ult_usuario")
            .replace_strict(nomes, default=None, return_dtype=pl.Utf8)
            .fill_null(pl.col("ult_usuario"))
            .fill_null("?")
        )
        .otherwise(pl.lit("—"))
        .alias("ult_contato")
    ).select("codcli", "ult_contato", "ult_quando", "ult_resultado")
    return meus.join(ultimo, on="codcli", how="left").sort(
        ["atrasadas", "prox_vcto"], descending=[True, False], nulls_last=True
    )


# -------------------------- relacionamento --------------------------------
def previa_relacionamento(ciclo: dict) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Simula a carteira do mês refeita pelo relacionamento (não salva).

    Usa SÓ os clientes que HOJE estão na faixa 16–60 dias (quem já está na carteira e
    continua na faixa + quem entrou depois). Quem saiu da faixa fica de fora.
    Devolve (nova distribuição, clientes que saem da carteira).
    """
    cart = carteira_salva(ciclo["id"])
    eleg = elegiveis()
    codigos = tuple(sorted(eleg["codcli"].to_list()))
    contatos = pl.from_pandas(q_contatos.relacionamento(codigos))
    if contatos.is_empty():
        contatos = pl.DataFrame(
            schema={
                "codcli": pl.Utf8,
                "cd_usuario": pl.Utf8,
                "dias_contato": pl.Int64,
                "ult_contato": pl.Date,
            }
        )
    acordos = acordos_com_responsavel()
    fechou = {}
    if not acordos.is_empty():
        fechou = {
            r["codcli"]: r["fechado_por"]
            for r in acordos.filter(
                pl.col("codcli").is_in(list(codigos)) & pl.col("fechado_por").is_not_null()
            ).iter_rows(named=True)
        }
    clientes = eleg.join(
        cart.select("codcli", pl.col("cod_usuario").alias("cod_antigo")), on="codcli", how="left"
    )
    nova = rel_mod.distribuir_por_relacionamento(clientes, cobradores(), contatos, fechou)
    saem = cart.filter(~pl.col("codcli").is_in(list(codigos))).select(
        "codcli",
        pl.col("cliente_ini").alias("cliente"),
        "loja_principal",
        pl.col("cod_usuario").alias("cod_antigo"),
    )
    return nova, saem


def aplicar_relacionamento(ciclo_id: int, nova: pl.DataFrame, saem: pl.DataFrame) -> int:
    """Salva: tira quem saiu da faixa, troca o cobrador de quem já estava (mantendo datas,
    anotações e recuperado) e inclui quem entrou na faixa depois."""
    store.remover_clientes(ciclo_id, saem["codcli"].to_list())
    ja_estavam = nova.filter(pl.col("cod_antigo").is_not_null())
    store.reatribuir(ciclo_id, list(ja_estavam.select("codcli", "cod_usuario").iter_rows()))
    novos = nova.filter(pl.col("cod_antigo").is_null())
    if not novos.is_empty():
        novos = novos.with_columns(
            pl.col("loja_principal")
            .replace_strict(config.PRIORIDADE_LOJA, default=99, return_dtype=pl.Int32)
            .alias("prioridade")
        )
        store.adicionar_clientes(ciclo_id, novos.to_pandas(), origem="relacionamento")
    return ja_estavam.filter(pl.col("cod_usuario") != pl.col("cod_antigo")).height + novos.height
