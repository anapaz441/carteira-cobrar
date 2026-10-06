"""Orquestra: busca os dados (camada data/) e aplica as regras (distribuicao/progresso).

As telas chamam só este módulo — nunca SQL direto.
"""

from datetime import date

import polars as pl

from data import carteira_store as store
from data.queries import contatos as q_contatos
from data.queries import titulos as q_titulos
from domain import distribuicao, progresso


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


def painel(ciclo: dict) -> pl.DataFrame:
    """Carteira do ciclo com débito atual, contatos e último contato — 1 linha por cliente."""
    cart = carteira_salva(ciclo["id"])
    if cart.is_empty():
        return pl.DataFrame()
    codigos = tuple(sorted(cart["codcli"].to_list()))
    inicio = date.fromisoformat(ciclo["inicio"])

    situacao = pl.from_pandas(q_titulos.situacao_atual(codigos))
    if situacao.is_empty():
        situacao = pl.DataFrame(
            schema={
                "codcli": pl.Utf8,
                "vl_vencido": pl.Float64,
                "vl_faixa": pl.Float64,
                "qt_titulos": pl.Int64,
                "cliente": pl.Utf8,
                "fantasia": pl.Utf8,
                "telefone": pl.Utf8,
                "whatsapp": pl.Utf8,
            }
        )
    contatos = pl.from_pandas(q_contatos.contatos_no_ciclo(inicio, codigos))
    ultimo = pl.from_pandas(q_contatos.ultimo_contato(codigos))
    if ultimo.is_empty():
        ultimo = pl.DataFrame(schema={"codcli": pl.Utf8, "ult_usuario": pl.Utf8})

    contagem = progresso.contar_contatos(contatos, cart)
    return progresso.montar_carteira(cart, situacao, contagem, ultimo, cobradores(False))


def contatos_do_ciclo(ciclo: dict) -> pl.DataFrame:
    """Ligações do ciclo (para o gráfico de contatos por dia)."""
    cart = carteira_salva(ciclo["id"])
    codigos = tuple(sorted(cart["codcli"].to_list()))
    inicio = date.fromisoformat(ciclo["inicio"])
    return pl.from_pandas(q_contatos.contatos_no_ciclo(inicio, codigos))


def historico(codcli: str) -> pl.DataFrame:
    return pl.from_pandas(q_contatos.historico_cliente(codcli))
