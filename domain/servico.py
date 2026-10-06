"""Orquestra: busca os dados (camada data/) e aplica as regras (distribuicao/progresso).

As telas chamam só este módulo — nunca SQL direto.
"""

from datetime import date

import polars as pl

import config
from data import carteira_store as store
from data.queries import contatos as q_contatos
from data.queries import titulos as q_titulos
from domain import distribuicao, progresso
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


def gerar_carteira(mes: str, inicio: date, dist: pl.DataFrame | None = None) -> int:
    """Gera e SALVA a carteira do mês (refaz se já existia).
    Se `dist` vier (a prévia que a pessoa conferiu), salva exatamente ela."""
    if dist is None:
        dist, _ = previa_distribuicao()
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


def _ligacoes_siac(inicio: date, codigos: tuple[str, ...]) -> pl.DataFrame:
    df = pl.from_pandas(q_contatos.contatos_no_ciclo(inicio, codigos))
    if df.is_empty():
        return pl.DataFrame(schema=_SCHEMA_LIGACOES)
    return df.select(list(_SCHEMA_LIGACOES)).cast(_SCHEMA_LIGACOES)


def _notas(codigos: tuple[str, ...], desde: str | None = None) -> pl.DataFrame:
    notas = store.anotacoes(list(codigos), desde=desde)
    return (
        pl.from_pandas(notas)
        if not notas.empty
        else pl.DataFrame(schema={c: pl.Utf8 for c in notas.columns})
    )


def contatos_do_ciclo(ciclo: dict) -> pl.DataFrame:
    """Todas as ligações do ciclo: SIAC + contatos registrados no app."""
    cart = carteira_salva(ciclo["id"])
    codigos = tuple(sorted(cart["codcli"].to_list()))
    inicio = date.fromisoformat(ciclo["inicio"])
    siac = _ligacoes_siac(inicio, codigos)
    app = progresso.anotacoes_como_contatos(_notas(codigos, desde=inicio.isoformat()))
    return pl.concat([siac, app.cast(_SCHEMA_LIGACOES)])


def painel(ciclo: dict) -> pl.DataFrame:
    """Carteira do ciclo com débito atual, contatos, recuperado e último contato
    — 1 linha por cliente."""
    cart = carteira_salva(ciclo["id"])
    if cart.is_empty():
        return pl.DataFrame()
    codigos = tuple(sorted(cart["codcli"].to_list()))

    situacao = pl.from_pandas(q_titulos.situacao_atual(codigos))
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
    siac_ult = pl.from_pandas(q_contatos.ultimo_contato(codigos))
    ultimo = progresso.combinar_ultimo(siac_ult, _notas(codigos))

    contagem = progresso.contar_contatos(contatos, cart)
    return progresso.montar_carteira(
        cart, situacao, contagem, ultimo, cobradores(False), recuperado
    )


def historico(codcli: str) -> pl.DataFrame:
    """Histórico do cliente: ligações do SIAC (120 dias) + anotações do app, juntas."""
    siac = pl.from_pandas(q_contatos.historico_cliente(codcli))
    nomes = dict(cobradores(False).select("cod_usuario", "nome").iter_rows())
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


def tipos_resultado() -> list[tuple[str, str]]:
    """Opções de resultado para registrar um contato no app (cobtpneg + "só anotação")."""
    tipos = pl.from_pandas(q_contatos.tipos_negociacao())
    opcoes = [(r["cd_negocia"], r["ds_negocia"]) for r in tipos.iter_rows(named=True)]
    return [*opcoes, (config.SO_ANOTACAO, "SÓ ANOTAÇÃO (não conta como contato)")]


def registrar_anotacao(codcli: str, cod_usuario: str, cd_negocia: str, texto: str) -> None:
    rotulos = dict(tipos_resultado())
    store.salvar_anotacao(codcli, cod_usuario, cd_negocia, rotulos.get(cd_negocia, ""), texto)


def rotina(
    ciclo: dict,
    cod_usuario: str,
    df_cobrador: pl.DataFrame,
    gerar: bool,
    tamanho: int = config.ROTINA_TAMANHO_PADRAO,
) -> list[str]:
    """Rotina de hoje do cobrador. Se `gerar`, monta uma nova e salva."""
    hoje = date.today()
    if gerar:
        feitos = rotina_mod.contatados_no_dia(contatos_do_ciclo(ciclo), hoje)
        lista = rotina_mod.selecionar_rotina(df_cobrador, feitos, tamanho)
        store.salvar_rotina(cod_usuario, hoje.isoformat(), lista)
        return lista
    return store.rotina_do_dia(cod_usuario, hoje.isoformat())


def contatados_hoje(ciclo: dict) -> set[str]:
    return rotina_mod.contatados_no_dia(contatos_do_ciclo(ciclo), date.today())
