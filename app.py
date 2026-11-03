from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# =========================================================
# 1. CONFIGURAÇÃO
# =========================================================

st.set_page_config(page_title="Painel Econômico Brasil", page_icon="📈", layout="wide")

CORES = {
    "fundo": "#0D1B24",
    "painel": "#13262F",
    "borda": "#2A4452",
    "texto": "#EAF2F5",
    "texto_secundario": "#9FB6C2",
}

# nome exibido -> (código da série no SGS do Banco Central, cor)
SERIES = {
    "Selic meta (% a.a.)": (432, "#F5A524"),
    "IPCA mensal (%)": (433, "#F2635B"),
    "IPCA 12 meses (%)": (13522, "#FF8A80"),
    "IGP-M mensal (%)": (189, "#C792EA"),
    "Dólar venda (R$)": (1, "#4FC3F7"),
    "Desemprego (%)": (24369, "#7BD88F"),
}

URL_BCB = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"

st.markdown(
    f"""
    <style>
    .stApp {{ background: {CORES["fundo"]}; color: {CORES["texto"]}; }}
    .block-container {{ max-width: 1400px; padding-top: 1.2rem; }}
    [data-testid="stSidebar"] {{ background: {CORES["painel"]}; border-right: 1px solid {CORES["borda"]}; }}
    [data-testid="stMetric"] {{ background: {CORES["painel"]}; border: 1px solid {CORES["borda"]};
        padding: 16px 18px; border-radius: 12px; }}
    [data-testid="stMetricLabel"] p {{ color: {CORES["texto_secundario"]} !important; }}
    [data-testid="stPlotlyChart"] {{ border: 1px solid {CORES["borda"]}; border-radius: 12px; padding: 6px; }}
    h1, h2, h3, h4, p, label {{ color: {CORES["texto"]}; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 2. DADOS (API pública do Banco Central)
# =========================================================

@st.cache_data(ttl=6 * 3600, show_spinner="Consultando a API do Banco Central...")
def buscar_serie(codigo: int, anos: int) -> pd.DataFrame:
    """Baixa uma série do SGS. Séries diárias aceitam no máximo 10 anos por consulta."""
    hoje = date.today()
    params = {
        "formato": "json",
        "dataInicial": (hoje - timedelta(days=365 * anos)).strftime("%d/%m/%Y"),
        "dataFinal": hoje.strftime("%d/%m/%Y"),
    }
    try:
        resposta = requests.get(URL_BCB.format(codigo=codigo), params=params, timeout=20)
        resposta.raise_for_status()
        df = pd.DataFrame(resposta.json())
    except (requests.RequestException, ValueError):
        return pd.DataFrame(columns=["data", "valor"])

    if df.empty:
        return pd.DataFrame(columns=["data", "valor"])
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    return df.dropna().sort_values("data").reset_index(drop=True)


def carregar(nome: str, anos: int) -> pd.DataFrame:
    return buscar_serie(SERIES[nome][0], anos)


def fmt(valor: float) -> str:
    """Formata no padrão brasileiro: 1.234,56"""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def estilizar(fig, altura: int = 400):
    fig.update_layout(
        template="plotly_dark",
        height=altura,
        paper_bgcolor=CORES["painel"],
        plot_bgcolor=CORES["painel"],
        margin=dict(l=18, r=18, t=50, b=20),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor="rgba(159,182,194,0.12)")
    fig.update_yaxes(gridcolor="rgba(159,182,194,0.12)")
    return fig


def grafico_linha(nome: str, df: pd.DataFrame, altura: int = 380):
    fig = px.line(df, x="data", y="valor", title=nome,
                  labels={"data": "Data", "valor": nome},
                  color_discrete_sequence=[SERIES[nome][1]])
    return estilizar(fig, altura)


# =========================================================
# 3. BARRA LATERAL
# =========================================================

st.sidebar.markdown("## 📈 Painel Econômico")
st.sidebar.caption("Dados do Banco Central do Brasil")
pagina = st.sidebar.radio(
    "Navegação",
    ["Visão geral", "Série histórica", "Comparador"],
    label_visibility="collapsed",
)
st.sidebar.divider()
anos = st.sidebar.slider("Período (anos)", 1, 10, 5)

st.title("Painel Econômico do Brasil")
st.caption(f"Últimos {anos} anos · atualizado em {date.today().strftime('%d/%m/%Y')}")


# =========================================================
# 4. PÁGINAS
# =========================================================

if pagina == "Visão geral":
    st.markdown("### Indicadores mais recentes")
    principais = ["Selic meta (% a.a.)", "IPCA 12 meses (%)", "Dólar venda (R$)", "Desemprego (%)"]
    for coluna, nome in zip(st.columns(4), principais):
        serie = carregar(nome, anos)
        with coluna:
            if serie.empty:
                st.metric(nome, "sem dados")
            else:
                atual, inicio = serie["valor"].iloc[-1], serie["valor"].iloc[0]
                st.metric(nome, fmt(atual), f"{atual - inicio:+.2f} desde o início do período",
                          delta_color="off")

    esq, dir_ = st.columns(2)
    for coluna, nome in zip((esq, dir_), ("Selic meta (% a.a.)", "Dólar venda (R$)")):
        serie = carregar(nome, anos)
        with coluna:
            if serie.empty:
                st.warning(f"Não foi possível carregar {nome}.")
            else:
                st.plotly_chart(grafico_linha(nome, serie), use_container_width=True)

elif pagina == "Série histórica":
    nome = st.selectbox("Indicador", list(SERIES))
    serie = carregar(nome, anos)

    if serie.empty:
        st.error("Não foi possível carregar essa série. Tente novamente em instantes.")
    else:
        usar_media = st.checkbox("Mostrar média móvel")
        fig = grafico_linha(nome, serie, 450)
        if usar_media:
            janela = st.slider("Janela da média (observações)", 3, 60, 12)
            serie["media_movel"] = serie["valor"].rolling(janela).mean()
            fig.add_scatter(x=serie["data"], y=serie["media_movel"], name=f"Média de {janela}",
                            line=dict(color="#FFFFFF", dash="dash"))
        st.plotly_chart(fig, use_container_width=True)

        a, b, c, d = st.columns(4)
        a.metric("Mínimo", fmt(serie["valor"].min()))
        b.metric("Média", fmt(serie["valor"].mean()))
        c.metric("Máximo", fmt(serie["valor"].max()))
        d.metric("Observações", len(serie))

        st.download_button("Baixar dados em CSV", serie.to_csv(index=False).encode("utf-8"),
                           file_name=f"{nome.split(' (')[0].lower().replace(' ', '_')}.csv",
                           mime="text/csv")

else:  # Comparador
    escolhidas = st.multiselect("Indicadores para comparar (2 ou mais)", list(SERIES),
                                default=["Selic meta (% a.a.)", "IPCA 12 meses (%)"])
    quadros = []
    for nome in escolhidas:
        serie = carregar(nome, anos)
        if not serie.empty:
            quadros.append(serie.set_index("data")["valor"].resample("MS").mean().rename(nome))

    if len(quadros) < 2:
        st.info("Escolha pelo menos dois indicadores com dados disponíveis.")
    else:
        mensal = pd.concat(quadros, axis=1).dropna()
        padronizado = (mensal - mensal.mean()) / mensal.std()

        fig = px.line(padronizado, title="Comparação padronizada (z-score, base mensal)",
                      labels={"value": "Desvios-padrão da média", "data": "Data", "variable": ""})
        st.plotly_chart(estilizar(fig, 450), use_container_width=True)

        corr = mensal.corr()
        fig_corr = px.imshow(corr, text_auto=".2f", zmin=-1, zmax=1,
                             color_continuous_scale="RdBu_r", title="Correlação entre os indicadores")
        st.plotly_chart(estilizar(fig_corr, 450), use_container_width=True)
        st.caption("Correlação não implica causalidade: use a matriz como ponto de partida para investigar.")

st.divider()
st.caption("Fonte: Banco Central do Brasil · Sistema Gerenciador de Séries Temporais (SGS).")
