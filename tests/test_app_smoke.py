"""Teste de fumaça: abre as telas com o banco SIAC simulado (sem rede)."""

import random
from datetime import date, timedelta

import pandas as pd
import polars as pl
import pytest
from streamlit.testing.v1 import AppTest

import config
from data.queries import acordos as q_acordos
from data.queries import contatos as q_contatos
from data.queries import titulos as q_titulos
from tests.conftest import RAIZ

HOJE = date.today()
COBS = ["8177", "3522", "8526", "2281", "4366", "4369"]


@pytest.fixture
def siac_falso(monkeypatch, tmp_path, clientes):
    monkeypatch.setattr(config, "CAMINHO_BANCO_CARTEIRA", str(tmp_path / "carteira.db"))
    base = clientes.to_pandas()
    base["cliente"] = "CLIENTE " + base["codcli"]
    base["fantasia"] = None
    base["telefone"] = "61 33330000"
    base["whatsapp"] = "61 999990000"
    base["telefones"] = "61999990000,6133330000"
    base["qt_faixa"] = 1
    base["dias_atraso_max"] = 30
    base["entrou_faixa_em"] = HOJE
    base["lojas"] = base["loja_principal"]
    base["email"] = None

    monkeypatch.setattr(q_titulos, "clientes_elegiveis", lambda: base.copy())
    monkeypatch.setattr(
        q_titulos,
        "situacao_atual",
        lambda codigos: base[base["codcli"].isin(codigos) & (base.index % 10 != 0)].copy(),
    )
    monkeypatch.setattr(
        q_titulos,
        "recuperado_na_faixa",
        lambda codigos, datas: pd.DataFrame(
            {"codcli": list(codigos)[:20], "qt_pagos": 1, "vl_recuperado": 100.0}
        ),
    )

    def contatos(inicio, codigos):
        rnd = random.Random(1)  # mesmo resultado a cada rerun
        linhas = [
            {
                "codcli": c,
                "dt_cobran": HOJE - timedelta(days=rnd.randint(1, 5)),
                "hr_cobran": "10:00:00",
                "cd_usuario": rnd.choice(COBS),
                "cd_negocia": rnd.choice(["04", "12", "11", "02"]),
            }
            for c in codigos
            for _ in range(rnd.randint(0, 7))
        ]
        return pd.DataFrame(linhas)

    monkeypatch.setattr(q_contatos, "contatos_no_ciclo", contatos)
    monkeypatch.setattr(
        q_contatos,
        "ultimo_contato",
        lambda codigos: pd.DataFrame(
            {
                "codcli": list(codigos),
                "ult_data": HOJE - timedelta(days=1),
                "ult_hora": "10:00:00",
                "ult_usuario": "8177",
                "ult_resultado": "TELEFONE NAO ATENDE",
                "ult_texto": "mandei msg no zap",
                "prox_ligacao": HOJE,
            }
        ),
    )
    monkeypatch.setattr(
        q_contatos,
        "historico_cliente",
        lambda codcli, dias=120: pd.DataFrame(
            {
                "data": [HOJE],
                "hora": ["10:00:00"],
                "cd_usuario": ["8177"],
                "loja": ["Gama"],
                "resultado": ["EM NEGOCIACAO"],
                "anotacao": ["ok"],
                "valor_cobrado": [100.0],
                "prox_ligacao": [HOJE],
            }
        ),
    )
    monkeypatch.setattr(
        q_contatos,
        "usuarios_que_cobraram",
        lambda dias=30: pd.DataFrame(
            {"cd_usuario": COBS, "ligacoes": 10, "clientes": 5, "ultima_ligacao": HOJE}
        ),
    )

    monkeypatch.setattr(
        q_acordos,
        "acordos_clientes",
        lambda codigos: pd.DataFrame(
            {
                "codcli": list(codigos)[:30],
                "situacao_acordo": (["A", "A", "I", "Q", "N"] * 6)[: len(list(codigos)[:30])],
                "dt_acordo": HOJE,
                "vl_acordo": 5000.0,
                "vl_parcela": 500.0,
                "parcelas": 10,
                "pagas": 3,
                "atrasadas": ([0, 1, 2, 0, 0] * 6)[: len(list(codigos)[:30])],
                "prox_vcto": HOJE + timedelta(days=3),
            }
        ),
    )
    monkeypatch.setattr(
        q_acordos,
        "acordos_ativos",
        lambda: pd.DataFrame(
            {
                "cd_loja": ["08", "07"],
                "sq_acordo": ["000001", "000002"],
                "codcli": list(base["codcli"][:2]),
                "cliente": ["CLIENTE A", "CLIENTE B"],
                "situacao_acordo": ["A", "A"],
                "dt_acordo": [HOJE, HOJE],
                "vl_acordo": [5000.0, 3000.0],
                "vl_parcela": [500.0, 300.0],
                "obs1": ["FIRMEI COM JOAO", "FIRMEI COM MARIA"],
                "obs2": ["CIENTE DO SERASA PEDRO", "GABRIEL"],
                "parcelas": [10, 10],
                "pagas": [3, 2],
                "atrasadas": [1, 0],
                "vl_atrasado": [500.0, 0.0],
                "prox_vcto": [HOJE, HOJE + timedelta(days=5)],
            }
        ),
    )

    monkeypatch.setattr(
        q_acordos,
        "titulos_para_acordo",
        lambda codcli: pd.DataFrame(
            {
                "cd_loja": ["06", "06", "04"],
                "codlan": ["1", "2", "3"],
                "duplicata": ["A/1", "A/2", "A/3"],
                "codcon": ["0021"] * 3,
                "vencimento": [HOJE - timedelta(days=d) for d in (40, 30, 20)],
                "valor": [700.0, 300.0, 250.0],
                "juros": [12.0] * 3,
                "multa": [3.0] * 3,
            }
        ),
    )

    def relac(codigos, dias=60):
        rnd = random.Random(2)
        return pd.DataFrame(
            [
                {
                    "codcli": c,
                    "cd_usuario": rnd.choice(COBS[:3]),
                    "dias_contato": rnd.randint(1, 8),
                    "ult_contato": HOJE,
                }
                for c in codigos
            ]
        )

    monkeypatch.setattr(q_contatos, "relacionamento", relac)
    monkeypatch.setattr(
        q_contatos,
        "tipos_negociacao",
        lambda: pd.DataFrame(
            {"cd_negocia": ["04", "11"], "ds_negocia": ["TELEFONE NAO ATENDE", "EM NEGOCIACAO"]}
        ),
    )


def _app(perfil=None, cod=None):
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=60)
    if perfil:
        at.session_state["perfil"] = perfil
        at.session_state["cod_usuario"] = cod
        at.session_state["nome_usuario"] = "teste"
    at.run()
    assert not at.exception, at.exception
    return at


def test_login_e_perfis(siac_falso):
    from data import carteira_store
    from domain import servico

    # Sem login: só a tela de entrar
    at = _app()
    assert at.radio[0].options == ["Sou cobrador(a)", "Sou gestor(a)"]

    # Gestora: escolhe o nome, sem senha
    at.radio[0].set_value("Sou gestor(a)").run()
    assert not at.text_input  # não pede matrícula nem senha
    sel = next(s for s in at.selectbox if s.label == "Seu nome")
    assert sel.options == ["Ana", "Angélica", "Carla"]
    sel.set_value("2184").run()
    at.button[0].click().run()
    assert at.session_state["perfil"] == "gestor"
    assert at.session_state["nome_usuario"] == "Angélica"
    assert at.session_state["cod_usuario"] == "2184"

    carteira_store.inicializar()
    servico.gerar_carteira(servico.mes_atual(), HOJE)

    # Gestor: todas as telas abrem
    for pagina in ("visao_geral", "carteira_cobrador", "gerar", "cobradores"):
        at = _app("gestor", "GESTOR")
        at.switch_page(f"views/{pagina}.py").run()
        assert not at.exception, (pagina, at.exception)

    # Cobrador: abre direto na carteira dele, sem escolher outro cobrador
    at = _app("cobrador", "8177")
    assert "Minha carteira" in at.title[0].value
    assert not [s for s in at.selectbox if s.label == "Cobrador"]
    assert at.metric[0].label == "Meus clientes"

    # Para o cobrador, as telas de gestão nem existem na navegação
    with pytest.raises(ValueError, match="Could not find a navigation page"):
        at.switch_page("views/gerar.py")


def test_rotina_e_anotacao(siac_falso):
    from data import carteira_store
    from domain import servico

    carteira_store.inicializar()
    servico.gerar_carteira(servico.mes_atual(), HOJE)

    at = _app("cobrador", "3522")
    gerar = next(b for b in at.button if "Gerar rotina" in b.label)
    gerar.click().run()
    assert not at.exception, at.exception
    rotina = carteira_store.rotina_do_dia("3522", HOJE.isoformat())
    assert len(rotina) == config.ROTINA_TAMANHO_PADRAO

    # Escreve uma anotação no 1º cliente da rotina
    cli = rotina[0]
    at.radio(key=f"tipo_rot_{cli}").set_value(config.CONTATO_EFETIVO)
    at.radio(key=f"canal_rot_{cli}").set_value("WhatsApp")
    at.text_area(key=f"txt_rot_{cli}").set_value("Falei com o dono, paga sexta.")
    form_btn = next(b for b in at.button if b.label == "💾 Salvar")
    form_btn.click().run()
    assert not at.exception, at.exception
    notas = carteira_store.anotacoes([cli])
    assert notas.iloc[0]["texto"] == "Falei com o dono, paga sexta."
    assert notas.iloc[0]["cod_usuario"] == "3522"
    assert notas.iloc[0]["canal"] == "WhatsApp"
    assert notas.iloc[0]["resultado"] == "CONTATO EFETIVO · WHATSAPP"
    # agora o cliente conta como contatado hoje
    assert cli in servico.contatados_hoje(carteira_store.obter_ciclo(servico.mes_atual()))


def test_atribuir_novos_na_visao_geral(siac_falso, monkeypatch):
    from data import carteira_store
    from domain import servico

    carteira_store.inicializar()
    # gera a carteira só com 140 clientes; os outros 11 viram "novos"
    dist, _ = servico.previa_distribuicao()
    servico.gerar_carteira(servico.mes_atual(), dist=dist.head(140))
    ciclo = carteira_store.obter_ciclo(servico.mes_atual())
    assert servico.clientes_novos(ciclo["id"]).height == 11

    at = _app("gestor", "2184")
    at.switch_page("views/visao_geral.py").run()
    assert not at.exception, at.exception
    botao = next(b for b in at.button if b.label.startswith("✅ Atribuir"))
    botao.click().run()
    assert not at.exception, at.exception
    assert servico.clientes_novos(ciclo["id"]).height == 0
    assert servico.carteira_salva(ciclo["id"]).height == 151


def test_meus_acordos_e_relacionamento(siac_falso):
    from data import carteira_store
    from domain import servico

    carteira_store.inicializar()
    dist, _ = servico.previa_distribuicao()
    servico.gerar_carteira(servico.mes_atual(), dist=dist.head(140))
    ciclo = carteira_store.obter_ciclo(servico.mes_atual())

    # Pedro vê o acordo dele, com alerta de parcela atrasada
    at = _app("cobrador", "8177")
    assert any("parcela atrasada" in e.value for e in at.error)

    # Gestor: prévia e aplicação pelo relacionamento
    at = _app("gestor", "2184")
    at.switch_page("views/gerar.py").run()
    next(b for b in at.button if "relacionamento" in b.label).click().run()
    assert not at.exception, at.exception
    next(c for c in at.checkbox if "aplicar" in c.label).check().run()
    next(b for b in at.button if b.label.startswith("✅ Aplicar")).click().run()
    assert not at.exception, at.exception
    cart = servico.carteira_salva(ciclo["id"])
    assert cart.height == 151  # só quem está na faixa hoje (inclui os 11 que entraram depois)
    por = dict(cart.group_by("cod_usuario").len().iter_rows())
    assert max(por.values()) <= 29
    # cliente com acordo do Gabriel ficou com o Gabriel
    acordo_gab = cart.filter(pl.col("codcli") == dist["codcli"].sort()[0])
    assert acordo_gab.height == 1


def test_rotina_inclui_acordo_atrasado(siac_falso):
    from data import carteira_store
    from domain import servico

    carteira_store.inicializar()
    servico.gerar_carteira(servico.mes_atual())
    # Pedro tem 1 acordo com parcela atrasada (cliente base[0])
    at = _app("cobrador", "8177")
    next(b for b in at.button if "Gerar rotina" in b.label).click().run()
    assert not at.exception, at.exception
    rot = carteira_store.rotina_do_dia("8177", HOJE.isoformat())
    ciclo = carteira_store.obter_ciclo(servico.mes_atual())
    atr = servico.clientes_acordo_atrasado(ciclo, "8177")
    assert rot[0] == atr["codcli"][0]
    assert any("ACORDO ATRASADO" in e.label for e in at.expander)


def test_simulador_no_cartao(siac_falso):
    from data import carteira_store
    from domain import servico

    carteira_store.inicializar()
    servico.gerar_carteira(servico.mes_atual())
    at = _app("cobrador", "3522")
    # simulador fica no fim da página, com o próprio seletor de cliente
    assert not any(t.label == "🧮 Simular acordo" for t in at.toggle)
    sel = next(s for s in at.selectbox if s.label == "Cliente para simular")
    sel.set_value(sel.options[0].split(" · ")[0]).run()
    assert not at.exception, at.exception
    assert any(m.label == "Juros (a.m.)" for m in at.metric)
    # títulos em 2 lojas → um acordo por loja, começando pela de maior débito (06)
    loja = next(r for r in at.radio if r.label == "Loja do acordo")
    assert loja.value == "06"
    principal = next(m for m in at.metric if m.label == "Principal")
    assert "1.000,00" in principal.value
    loja.set_value("04").run()
    assert not at.exception, at.exception
    principal = next(m for m in at.metric if m.label == "Principal")
    assert "250,00" in principal.value
    next(r for r in at.radio if r.label == "Loja do acordo").set_value("06").run()
    # desconto: valor menor → juros < 11,80% → aviso de não autorizado
    valor = next(n for n in at.number_input if n.label == "Valor do acordo (R$)")
    valor.set_value(1050.0).run()
    assert not at.exception, at.exception
    assert any("NÃO AUTORIZADO" in w.value for w in at.warning)


def test_cliente_de_um_cobrador_so(siac_falso):
    """Cliente com acordo assinado pelo Pedro, mas na carteira de outro cobrador:
    aparece SÓ para o dono da carteira (nunca para os dois)."""
    from data import carteira_store
    from domain import servico

    carteira_store.inicializar()
    servico.gerar_carteira(servico.mes_atual())
    ciclo = carteira_store.obter_ciclo(servico.mes_atual())
    cli = servico.acordos_com_responsavel()["codcli"][0]  # acordo assinado pelo Pedro
    carteira_store.mover_cliente(ciclo["id"], cli, "3522")

    assert cli not in servico.meus_acordos("8177", ciclo)["codcli"].to_list()
    assert cli in servico.meus_acordos("3522", ciclo)["codcli"].to_list()
    donos = [
        c
        for c in ("8177", "3522", "8526", "2281", "4366", "4369")
        if cli in servico.meus_acordos(c, ciclo)["codcli"].to_list()
    ]
    assert donos == ["3522"]

    # adicionar de novo o mesmo cliente não troca o cobrador
    novo = servico.distribuicao.distribuir(
        servico.elegiveis().filter(pl.col("codcli") == cli), servico.cobradores()
    ).with_columns(pl.lit("4369").alias("cod_usuario"))
    carteira_store.adicionar_clientes(ciclo["id"], novo.to_pandas())
    cart = servico.carteira_salva(ciclo["id"]).filter(pl.col("codcli") == cli)
    assert cart.height == 1 and cart["cod_usuario"][0] == "3522"
