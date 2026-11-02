import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3

# Configuração da página
st.set_page_config(page_title="Analytics Imobiliário - Brasília", layout="wide")

# Carregar os dados
@st.cache_data
def carregar_dados():
    conn = sqlite3.connect('imoveis.db')
    query = '''
        SELECT 
            bairro, 
            tipo_imovel, 
            area_m2, 
            preco_aluguel, 
            (preco_aluguel / NULLIF(area_m2, 0)) AS preco_m2,
            latitude, 
            longitude 
        FROM imoveis_locacao
    '''
    df = pd.read_sql(query, conn)
    conn.close()
    return df

st.title("Painel de Inteligência Imobiliária - Brasília")
st.markdown("Monitoramento de preços de Kitnets e Edículas para suporte a decisões de aluguel e investimentos.")

df = carregar_dados()

# Filtros na barra lateral
st.sidebar.header("Filtros Analíticos")
bairro_selecionado = st.sidebar.multiselect(
    "Selecione as Regiões", 
    options=df['bairro'].unique(),
    default=df['bairro'].unique()
)

df_filtrado = df[df['bairro'].isin(bairro_selecionado)]

# Renderizar métricas e gráficos se houver dados
if not df_filtrado.empty:
    col1, col2, col3 = st.columns(3)
    col1.metric("Média de Aluguel", f"R$ {df_filtrado['preco_aluguel'].mean():.2f}")
    col2.metric("Preço Médio / m²", f"R$ {df_filtrado['preco_m2'].mean():.2f}")
    col3.metric("Total de Imóveis Analisados", len(df_filtrado))

    st.subheader("Mapa de Preços por Região (R$/m²)")
    fig_map = px.scatter_mapbox(
        df_filtrado, 
        lat="latitude", 
        lon="longitude", 
        color="preco_m2", 
        size="preco_aluguel",
        hover_name="bairro", 
        hover_data=["tipo_imovel", "area_m2"],
        color_continuous_scale=px.colors.cyclical.IceFire, 
        size_max=15, 
        zoom=11,
        mapbox_style="carto-positron"
    )
    st.plotly_chart(fig_map, use_container_width=True)

    st.subheader("Distribuição de Valores por Bairro")
    fig_bar = px.box(df_filtrado, x="bairro", y="preco_aluguel", color="tipo_imovel")
    st.plotly_chart(fig_bar, use_container_width=True)
else:
    st.warning("Por favor, selecione pelo menos um bairro na barra lateral.")
