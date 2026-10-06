"""Simulador de acordo — reproduz as contas da tela de Acordos do SIAC (ACO000.prg).

Funções puras (sem Streamlit, sem SQL). Referências no fonte do SIAC:
- fCarregaDuplicatas_Aco  → juros e multa de cada título (linhas ~1053-1059)
- fCalculaPercentualJuros → valor negociado menor → acha o % de juros (bisseção, ~1248)
- Get nQt_Parcela/nVl_Parcela → parcelamento por quantidade ou por valor (~468-479)
- fMostraValorParcelas    → N-1 parcelas iguais + última com a diferença (~1227)
- fAtribuiPrimeiroVencimento / fValidaPrimeiroVcto → 1º vencimento (~1150-1222)
- Aco_Inc                 → juros >= 11,80% e multa >= 3% = acordo ATIVO; senão "N" (~157)
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

import config


def _r2(v: float) -> float:
    """Arredonda como o Clipper Val(Str(x,15,2)) (meio para cima)."""
    return float(f"{v + (1e-9 if v >= 0 else -1e-9):.2f}")


@dataclass
class Titulo:
    codlan: str
    duplicata: str
    vencimento: date
    valor: float
    juros_titulo: float  # % gravado no título (lanca.juros)
    multa_titulo: float  # % gravado no título (lanca.multa)


@dataclass
class LinhaTitulo:
    titulo: Titulo
    dias: int
    juros: float
    multa: float

    @property
    def total(self) -> float:
        return self.titulo.valor + self.juros + self.multa


def calcular_titulos(
    titulos: list[Titulo],
    data_acordo: date,
    pc_juros: float | None = None,
    pc_multa: float | None = None,
) -> list[LinhaTitulo]:
    """Juros e multa de cada título na data do acordo.

    pc_juros/pc_multa = None → usa o % gravado em cada título (padrão do SIAC);
    informado → usa o % informado (como quando o cobrador altera o campo na tela).
    Juros: valor × (%/100) / 30 × dias de atraso. Multa: valor × % / 100 (se o título tem multa).
    """
    linhas = []
    for t in titulos:
        dias = (data_acordo - t.vencimento).days
        if pc_multa is None:
            taxa_multa = t.multa_titulo
        else:
            taxa_multa = pc_multa
        multa = _r2(t.valor * taxa_multa / 100) if (t.multa_titulo > 0 and dias > 0) else 0.0
        if pc_juros is None:
            taxa_juros = t.juros_titulo if t.juros_titulo > 0 else config.ACORDO_JUROS_MES
        else:
            taxa_juros = pc_juros
        juros = _r2(t.valor * (taxa_juros / 100) / 30 * max(dias, 0)) if dias > 0 else 0.0
        linhas.append(LinhaTitulo(t, dias, juros, multa))
    return linhas


def totais(linhas: list[LinhaTitulo]) -> tuple[float, float, float, float]:
    """(principal, juros, multa, total atualizado)"""
    principal = _r2(sum(linha.titulo.valor for linha in linhas))
    juros = _r2(sum(linha.juros for linha in linhas))
    multa = _r2(sum(linha.multa for linha in linhas))
    return principal, juros, multa, _r2(principal + juros + multa)


def juros_para_valor(
    titulos: list[Titulo], data_acordo: date, valor_desejado: float, pc_multa: float
) -> tuple[float | None, float]:
    """Acha o % de juros que faz o total bater com o valor negociado (bisseção, como o SIAC).
    Devolve (pc_juros, total_obtido). pc_juros None = "valor impossível" (nem com 0% bate)."""
    alvo = _r2(valor_desejado)
    inf, sup, pc = 0.0, config.ACORDO_JUROS_MES, config.ACORDO_JUROS_MES
    principal = _r2(sum(t.valor for t in titulos))
    if alvo == principal:
        pc = 0.0
    total = 0.0
    for _ in range(80):
        total = totais(calcular_titulos(titulos, data_acordo, pc, pc_multa))[3]
        if total == alvo:
            return pc, total
        if total > alvo:
            sup = pc
            pc = pc - (pc - inf) / 2
        else:
            inf = pc
            pc = pc + (sup - pc) / 2
        if pc < 1e-8:
            break
    total0 = totais(calcular_titulos(titulos, data_acordo, 0.0, pc_multa))[3]
    if total0 > alvo:
        return None, total0
    return pc, total


def primeiro_vencimento(hoje: date, periodicidade: str, dia: str) -> date:
    """Sugestão do 1º vencimento (fAtribuiPrimeiroVencimento).
    periodicidade S/Q: `dia` é o dia da semana do SIAC ('02'=segunda ... '06'=sexta).
    periodicidade M:   `dia` é o dia do mês (1 a 28)."""
    if periodicidade == "M":
        d = date(hoje.year, hoje.month, int(dia))
        return d if d >= hoje else _soma_meses(d, 1)
    # Dow do Clipper: 1 = domingo ... 7 = sábado
    dow_hoje = (hoje.isoweekday() % 7) + 1
    alvo = int(dia)
    if dow_hoje <= alvo:
        return hoje + timedelta(days=alvo - dow_hoje)
    return hoje + timedelta(days=7 - (dow_hoje - alvo))


def _soma_meses(d: date, n: int) -> date:
    mes = d.month - 1 + n
    ano = d.year + mes // 12
    mes = mes % 12 + 1
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


@dataclass
class Parcelamento:
    total: float
    quantidade: int
    valor_parcela: float
    parcelas: list[tuple[int, date, float]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def parcelar(
    total: float,
    modo: str,
    valor_ou_qtd: float,
    periodicidade: str,
    primeiro: date,
    hoje: date,
) -> Parcelamento:
    """modo 'V' (informa o valor da parcela) ou 'Q' (informa a quantidade).
    Todas as parcelas iguais, e a última leva a diferença (fMostraValorParcelas)."""
    avisos = []
    if modo == "Q":
        qtd = max(int(valor_ou_qtd), 1)
        parc = _r2(total / qtd)
        if _r2(parc * qtd) < _r2(total):
            parc = _r2(parc + 0.01)
    else:
        parc = _r2(valor_ou_qtd)
        qtd = int((total / parc) + 0.99) if parc > 0 else 0
    if parc < config.ACORDO_PARCELA_MIN:
        avisos.append(f"Parcela abaixo do mínimo do SIAC (R$ {config.ACORDO_PARCELA_MIN:.2f}).")
    if (primeiro - hoje).days > config.ACORDO_PRIMEIRO_VCTO_MAX_DIAS:
        avisos.append(
            f"O 1º vencimento precisa ser em até {config.ACORDO_PRIMEIRO_VCTO_MAX_DIAS} dias."
        )
    if primeiro < hoje:
        avisos.append("O 1º vencimento não pode ser no passado.")

    parcelas = []
    for i in range(qtd):
        if periodicidade == "S":
            venc = primeiro + timedelta(days=7 * i)
        elif periodicidade == "Q":
            venc = primeiro + timedelta(days=14 * i)
        else:
            venc = _soma_meses(primeiro, i)
        valor = parc if i < qtd - 1 else _r2(total - (qtd - 1) * parc)
        parcelas.append((i + 1, venc, valor))
    return Parcelamento(total, qtd, parc, parcelas, avisos)


def situacao_prevista(pc_juros: float, pc_multa: float) -> tuple[str, str]:
    """Como o SIAC grava o acordo: juros >= 11,80% e multa >= 3% → ATIVO;
    senão → NÃO AUTORIZADO (precisa de autorização da gestão)."""
    if pc_juros >= config.ACORDO_JUROS_MIN_AUTOMATICO and pc_multa >= config.ACORDO_MULTA:
        return "A", "✅ Entra ATIVO direto no SIAC"
    return "N", "⚠️ Fica NÃO AUTORIZADO no SIAC — precisa de autorização da gestão"
