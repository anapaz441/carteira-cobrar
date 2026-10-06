"""Regras de RELACIONAMENTO (funções puras, sem Streamlit):

- quem_fechou: descobre, pela observação do acordo no SIAC, qual cobrador fechou o acordo
  (eles assinam o nome no fim: "... CIENTE DO SERASA PEDRO").
- distribuir_por_relacionamento: monta a carteira mantendo cada cliente com quem já fala
  com ele, respeitando um TETO por cobrador (a fatia justa) para não sobrecarregar ninguém.
"""

import re
import unicodedata

import polars as pl

from domain import distribuicao

MOTIVO_ACORDO = "Fechou o acordo"
MOTIVO_CONTATO = "Quem mais falou com o cliente"
MOTIVO_SEGUNDO = "Também já falou com o cliente"
MOTIVO_EQUILIBRIO = "Equilíbrio (sem relacionamento disponível)"


def _normalizar(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode()
    return txt.upper()


def quem_fechou(obs1: str, obs2: str, nomes: dict[str, str]) -> str | None:
    """Código do cobrador cujo nome aparece POR ÚLTIMO nas observações do acordo.
    (A assinatura fica no fim; nomes no começo costumam ser do cliente: "FIRMEI COM PEDRO".)"""
    texto = _normalizar(f"{obs1} {obs2}")
    melhor, pos_melhor = None, -1
    # Assinaturas compostas conhecidas (ex.: "PEDRO PAULO" = Pedro) valem como um nome só
    for assinatura, cod in distribuicao.config.ASSINATURAS_ACORDO.items():
        for m in re.finditer(rf"\b{re.escape(assinatura)}\b", texto):
            if m.start() >= pos_melhor:
                melhor, pos_melhor = cod, m.start()
            texto = texto[: m.start()] + "#" * len(assinatura) + texto[m.end() :]
    for cod, nome in nomes.items():
        primeiro_nome = _normalizar(nome).split()[0] if nome else ""
        if len(primeiro_nome) < 3:
            continue
        for m in re.finditer(rf"\b{re.escape(primeiro_nome)}\b", texto):
            if m.start() > pos_melhor:
                melhor, pos_melhor = cod, m.start()
    return melhor


def marcar_quem_fechou(acordos: pl.DataFrame, nomes: dict[str, str]) -> pl.DataFrame:
    """Acrescenta a coluna `fechado_por` (código do cobrador ou nulo)."""
    if acordos.is_empty():
        return acordos.with_columns(pl.lit(None, dtype=pl.Utf8).alias("fechado_por"))
    return acordos.with_columns(
        pl.struct("obs1", "obs2")
        .map_elements(lambda r: quem_fechou(r["obs1"], r["obs2"], nomes), return_dtype=pl.Utf8)
        .alias("fechado_por")
    )


def distribuir_por_relacionamento(
    clientes: pl.DataFrame,
    cobradores: pl.DataFrame,
    contatos: pl.DataFrame,
    fechou_acordo: dict[str, str],
) -> pl.DataFrame:
    """Devolve `clientes` com cod_usuario e motivo.

    clientes:      codcli, loja_principal, vl_faixa, vl_vencido (+ outras)
    cobradores:    cod_usuario, tipo (ativos)
    contatos:      codcli, cd_usuario, dias_contato, ult_contato (últimos 60 dias)
    fechou_acordo: codcli -> cod_usuario de quem fechou o acordo ATIVO do cliente

    Regra (combinada com a Ana em 06/10/2026):
    1. Quem fechou o acordo ativo tem prioridade; depois quem mais falou com o cliente
       (mais dias com ligação; empate = ligação mais recente); depois o 2º, 3º...
    1b. Clientes das lojas críticas escolhem primeiro (Goiânia → ... → Recife).
    2. Cada cobrador tem TETO = fatia justa de clientes (integral ~19%, parcial ~14%).
       Se o preferido já está cheio, tenta o próximo da lista do cliente.
    3. Quem sobrar (sem relacionamento ou todos cheios) é distribuído pela regra de
       equilíbrio normal (quantidade, valor e loja).
    """
    ativos = set(cobradores["cod_usuario"].to_list())
    share = distribuicao.fatias(cobradores)
    n = clientes.height
    teto = {cod: max(1, round(s * n)) for cod, s in share.items()}
    carga = dict.fromkeys(ativos, 0)

    rel = contatos.filter(pl.col("cd_usuario").is_in(list(ativos))).sort(
        ["codcli", "dias_contato", "ult_contato"], descending=[False, True, True]
    )
    preferidos: dict[str, list[str]] = {}
    for r in rel.iter_rows(named=True):
        preferidos.setdefault(r["codcli"], []).append(r["cd_usuario"])

    # Força do vínculo: acordo primeiro, depois quem tem mais dias de contato com o "dono"
    forca = {
        r["codcli"]: r["dias_contato"]
        for r in rel.unique("codcli", keep="first", maintain_order=True).iter_rows(named=True)
    }
    # Ordem de escolha: acordo → loja mais crítica → vínculo mais forte → maior débito.
    # Assim os clientes das lojas críticas pegam primeiro o cobrador com quem já falam.
    ordem = clientes.with_columns(
        pl.col("codcli")
        .is_in([c for c, u in fechou_acordo.items() if u in ativos])
        .alias("_tem_acordo"),
        pl.col("loja_principal")
        .replace_strict(distribuicao.config.PRIORIDADE_LOJA, default=99, return_dtype=pl.Int32)
        .alias("_prio_loja"),
        pl.col("codcli").replace_strict(forca, default=0, return_dtype=pl.Int64).alias("_forca"),
    ).sort(
        ["_tem_acordo", "_prio_loja", "_forca", "vl_faixa"], descending=[True, False, True, True]
    )

    escolha: dict[str, tuple[str, str]] = {}
    for r in ordem.iter_rows(named=True):
        cod = r["codcli"]
        candidatos: list[tuple[str, str]] = []
        dono_acordo = fechou_acordo.get(cod)
        if dono_acordo in ativos:
            candidatos.append((dono_acordo, MOTIVO_ACORDO))
        for i, u in enumerate(preferidos.get(cod, [])):
            if u != dono_acordo:
                candidatos.append((u, MOTIVO_CONTATO if i == 0 else MOTIVO_SEGUNDO))
        for u, motivo in candidatos:
            if carga[u] < teto[u]:
                escolha[cod] = (u, motivo)
                carga[u] += 1
                break

    # 3. Sobra: vai para quem está mais longe do teto (quantidade) e, no empate,
    #    com menos débito 16–60d — loja mais crítica e maior débito primeiro.
    valor = dict.fromkeys(ativos, 0.0)
    for cod, (u, _) in escolha.items():
        valor[u] += float(ordem.filter(pl.col("codcli") == cod)["vl_faixa"][0] or 0)
    v_total = max(float(clientes["vl_faixa"].sum() or 0), 1.0)
    sobra = (
        ordem.filter(~pl.col("codcli").is_in(list(escolha)))
        .with_columns(
            pl.col("loja_principal")
            .replace_strict(distribuicao.config.PRIORIDADE_LOJA, default=99, return_dtype=pl.Int32)
            .alias("_prio")
        )
        .sort(["_prio", "vl_faixa"], descending=[False, True])
    )
    for r in sobra.iter_rows(named=True):
        u = min(
            ativos,
            key=lambda k: (carga[k] / teto[k], valor[k] / (share[k] * v_total), k),
        )
        escolha[r["codcli"]] = (u, MOTIVO_EQUILIBRIO)
        carga[u] += 1
        valor[u] += float(r["vl_faixa"] or 0)

    return ordem.drop("_tem_acordo", "_forca", "_prio_loja").with_columns(
        pl.col("codcli").replace_strict({k: v[0] for k, v in escolha.items()}).alias("cod_usuario"),
        pl.col("codcli").replace_strict({k: v[1] for k, v in escolha.items()}).alias("motivo"),
    )
