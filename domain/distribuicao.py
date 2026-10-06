"""Regra de distribuição da carteira entre os cobradores (funções puras, sem Streamlit).

Como funciona, em português:
1. Cada cobrador tem um PESO: integral = 1, parcial = 0,75 (1/4 a menos).
   A "fatia justa" dele é peso / soma dos pesos.
   Ex.: 3 integrais + 3 parciais → integral ≈ 19% da carteira, parcial ≈ 14%.
2. Os clientes são distribuídos um a um, começando pela loja mais crítica
   (Goiânia → Planaltina → Ceilândia → Gama → SOF → Asa Norte → Recife) e,
   dentro da loja, do maior débito para o menor.
3. Cada cliente vai para o cobrador que está MAIS LONGE da fatia justa dele,
   olhando ao mesmo tempo: quantidade de clientes, valor e quantidade daquela loja.
   Assim todos ficam com quantidade e valor proporcionais, e as lojas críticas
   ficam espalhadas entre todos (ninguém fica só com Recife, por exemplo).
"""

from dataclasses import dataclass, field

import polars as pl

import config


@dataclass
class _Carga:
    """O que um cobrador já tem na mão durante a distribuição."""

    share: float
    qtd: int = 0
    valor: float = 0.0
    por_loja: dict[str, int] = field(default_factory=dict)


def fatias(cobradores: pl.DataFrame) -> dict[str, float]:
    """Fatia justa de cada cobrador (soma = 1). Espera colunas cod_usuario, tipo."""
    pesos = {
        r["cod_usuario"]: config.PESO_TIPO[r["tipo"]] for r in cobradores.iter_rows(named=True)
    }
    total = sum(pesos.values())
    return {cod: p / total for cod, p in pesos.items()}


def distribuir(
    clientes: pl.DataFrame,
    cobradores: pl.DataFrame,
    carteira_atual: pl.DataFrame | None = None,
    coluna_valor: str = config.METRICA_VALOR_EQUILIBRIO,
) -> pl.DataFrame:
    """Devolve `clientes` com a coluna `cod_usuario` (cobrador escolhido).

    clientes:       codcli, loja_principal, <coluna_valor> (+ quaisquer outras colunas)
    cobradores:     cod_usuario, tipo ('Integral'/'Parcial') — só os ativos
    carteira_atual: (opcional) clientes já distribuídos no ciclo, com cod_usuario,
                    loja_principal e <coluna_valor>. Usado para encaixar clientes NOVOS
                    sem mexer em quem já está na carteira.
    """
    if cobradores.is_empty():
        raise ValueError("Cadastre pelo menos um cobrador ativo.")
    if clientes.is_empty():
        return clientes.with_columns(pl.lit(None, dtype=pl.Utf8).alias("cod_usuario"))

    share = fatias(cobradores)
    cargas = {cod: _Carga(share=s) for cod, s in share.items()}

    # Carga que já existe (modo "distribuir novos")
    base = (
        carteira_atual.filter(pl.col("cod_usuario").is_in(list(cargas)))
        if carteira_atual is not None and not carteira_atual.is_empty()
        else None
    )
    if base is not None:
        for r in base.iter_rows(named=True):
            c = cargas[r["cod_usuario"]]
            c.qtd += 1
            c.valor += float(r[coluna_valor] or 0)
            c.por_loja[r["loja_principal"]] = c.por_loja.get(r["loja_principal"], 0) + 1

    # Totais "finais" (o que existirá depois de distribuir), para medir a fatia justa
    todos = clientes.select("loja_principal", coluna_valor)
    if base is not None:
        todos = pl.concat([todos, base.select("loja_principal", coluna_valor)])
    n_total = todos.height
    v_total = max(float(todos[coluna_valor].sum() or 0), 1.0)
    n_loja = dict(todos.group_by("loja_principal").len().iter_rows())

    # Ordem: loja mais crítica primeiro, maior valor primeiro
    ordenados = clientes.with_columns(
        pl.col("loja_principal")
        .replace_strict(config.PRIORIDADE_LOJA, default=99, return_dtype=pl.Int32)
        .alias("prioridade")
    ).sort(["prioridade", coluna_valor], descending=[False, True])

    escolhidos: list[str] = []
    for r in ordenados.iter_rows(named=True):
        loja = r["loja_principal"]
        valor = float(r[coluna_valor] or 0)

        def custo(c: _Carga, loja=loja, valor=valor) -> float:
            # Quanto o cobrador ficaria "acima da fatia" se recebesse este cliente
            q = (c.qtd + 1) / (c.share * n_total)
            v = (c.valor + valor) / (c.share * v_total)
            lj = (c.por_loja.get(loja, 0) + 1) / (c.share * n_loja[loja])
            return (
                config.PESO_EQUILIBRIO_QTD * q
                + config.PESO_EQUILIBRIO_VALOR * v
                + config.PESO_EQUILIBRIO_LOJA * lj
            )

        cod = min(cargas, key=lambda k: (custo(cargas[k]), -cargas[k].share, k))
        c = cargas[cod]
        c.qtd += 1
        c.valor += valor
        c.por_loja[loja] = c.por_loja.get(loja, 0) + 1
        escolhidos.append(cod)

    # Só refinamos a distribuição completa. No modo "novos" os clientes antigos não mudam.
    if base is None:
        # Valor secundário: se equilibramos pelo débito 16–60d, também tentamos
        # aproximar o débito vencido TOTAL (com peso menor).
        secundaria = "vl_vencido" if coluna_valor != "vl_vencido" else None
        if secundaria and secundaria in ordenados.columns:
            v2 = ordenados[secundaria].fill_null(0).cast(pl.Float64).to_list()
        else:
            v2 = [0.0] * ordenados.height
        escolhidos = _refinar_por_trocas(
            ordenados["loja_principal"].to_list(),
            ordenados[coluna_valor].fill_null(0).cast(pl.Float64).to_list(),
            v2,
            escolhidos,
            share,
        )
    return ordenados.with_columns(pl.Series("cod_usuario", escolhidos, dtype=pl.Utf8))


def _refinar_por_trocas(
    lojas: list[str],
    valores: list[float],
    valores2: list[float],
    donos: list[str],
    share: dict[str, float],
    peso2: float = config.PESO_VALOR_SECUNDARIO,
    max_passadas: int = 20,
) -> list[str]:
    """Ajuste fino: troca clientes DA MESMA LOJA entre dois cobradores quando isso
    aproxima o valor de cada um da sua fatia justa. Como a troca é 1 por 1 e na
    mesma loja, a quantidade de clientes e a divisão por loja não mudam."""
    donos = list(donos)
    t1 = max(sum(valores), 1.0)
    t2 = max(sum(valores2), 1.0)
    c1 = dict.fromkeys(share, 0.0)
    c2 = dict.fromkeys(share, 0.0)
    for d, v, w in zip(donos, valores, valores2, strict=True):
        c1[d] += v
        c2[d] += w

    def desvio(cod: str, v1: float, v2: float) -> float:
        s = share[cod]
        return ((v1 / t1 - s) ** 2 + peso2 * (v2 / t2 - s) ** 2) / s

    n = len(donos)
    for _ in range(max_passadas):
        melhorou = False
        for i in range(n):
            for j in range(i + 1, n):
                a, b = donos[i], donos[j]
                if a == b or lojas[i] != lojas[j]:
                    continue
                # quanto A ganha (e B perde) se trocarem os clientes i e j
                d1 = valores[j] - valores[i]
                d2 = valores2[j] - valores2[i]
                antes = desvio(a, c1[a], c2[a]) + desvio(b, c1[b], c2[b])
                depois = desvio(a, c1[a] + d1, c2[a] + d2) + desvio(b, c1[b] - d1, c2[b] - d2)
                if depois < antes - 1e-12:
                    donos[i], donos[j] = b, a
                    c1[a] += d1
                    c1[b] -= d1
                    c2[a] += d2
                    c2[b] -= d2
                    melhorou = True
        if not melhorou:
            break
    return donos


def resumo_equilibrio(
    distribuicao: pl.DataFrame,
    cobradores: pl.DataFrame,
    coluna_valor: str = config.METRICA_VALOR_EQUILIBRIO,
) -> pl.DataFrame:
    """Tabela de conferência: % de clientes e % de valor de cada cobrador vs. fatia justa."""
    share = fatias(cobradores)
    agg = distribuicao.group_by("cod_usuario").agg(
        pl.len().alias("clientes"),
        pl.col(coluna_valor).sum().alias("valor"),
        pl.col("vl_vencido").sum().alias("vl_vencido")
        if "vl_vencido" in distribuicao.columns
        else pl.lit(0.0).alias("vl_vencido"),
    )
    tot_n = max(agg["clientes"].sum(), 1)
    tot_v = max(float(agg["valor"].sum() or 0), 1.0)
    return (
        cobradores.select("cod_usuario", "nome", "tipo")
        .join(agg, on="cod_usuario", how="left")
        .with_columns(
            pl.col("clientes").fill_null(0),
            pl.col("valor").fill_null(0.0),
            pl.col("vl_vencido").fill_null(0.0),
            pl.col("cod_usuario").replace_strict(share, return_dtype=pl.Float64).alias("fatia"),
        )
        .with_columns(
            (pl.col("clientes") / tot_n).alias("pct_clientes"),
            (pl.col("valor") / tot_v).alias("pct_valor"),
        )
        .sort("tipo", "nome")
    )
