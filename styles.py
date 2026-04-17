"""
Módulo de Design e Identidade Visual - styles.py

Este módulo define a estética corporativa do BOI GENE Pro:
- Customização CSS: Injeta estilos personalizados no Streamlit para alterar fontes (Inter), 
  esquemas de cores (Azul Profundo e Verde Lucro) e arredondamento de bordas.
- Componentes de UI: Define o design visual dos 'Cards de Validação' (Success, Warning, Error), 
  formatando alertas visuais para o consultor.
- Configuração Gráfica: Sincroniza o tema do Matplotlib com o tema claro do dashboard, 
  garantindo que todos os gráficos exportados mantenham uma identidade visual coerente.

Garante que a experiência do usuário seja profissional, intuitiva e focada na 
legibilidade de dados técnicos.
"""

import streamlit as st
import matplotlib.pyplot as plt

def apply_custom_css():
    """Aplica o CSS customizado para o tema claro e consultoria."""
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
        
        html, body, [class*="css"] { 
            font-family: 'Inter', sans-serif; 
            color: #333333;
        }
        
        /* Fundo Principal */
        .stApp { background-color: #FFFFFF; }
        
        /* Sidebar */
        [data-testid="stSidebar"] {
            background-color: #F8F9FA;
            border-right: 1px solid #E9ECEF;
        }
        
        /* Títulos */
        h1, h2, h3 { 
            color: #0C2D48 !important; 
            font-weight: 700;
            letter-spacing: -0.5px;
        }
        
        /* Subtítulos e Textos */
        h4, h5, label, .stMarkdown p {
            color: #495057 !important;
        }
        
        /* Centralizar a imagem no Menu */
        [data-testid="stSidebar"] img {
            display: block;
            margin-left: auto;
            margin-right: auto;
            max-width: 80%;
            margin-bottom: 20px;
            filter: drop-shadow(0px 4px 6px rgba(0,0,0,0.1));
        }
        
        /* Cards de Validação */
        .validation-card {
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 15px;
            background-color: #FFFFFF;
            border: 1px solid #DEE2E6;
            border-left-width: 6px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            color: #333;
        }
        .valid-success { border-left-color: #2E7D32; } /* Verde Lucro */
        .valid-warning { border-left-color: #FFB300; } /* Amarelo Atenção */
        .valid-error { border-left-color: #C62828; }   /* Vermelho Risco */
        
        /* Métricas */
        [data-testid="stMetricValue"] {
            font-size: 2rem !important;
            font-weight: 700 !important;
            color: #0C2D48 !important;
        }
        [data-testid="stMetricLabel"] {
            color: #6C757D !important;
            font-size: 0.9rem !important;
        }
        
        /* Botões */
        div.stButton > button {
            background-color: #2E7D32;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 0.5rem 1rem;
            font-weight: 600;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: all 0.3s;
        }
        div.stButton > button:hover {
            background-color: #1B5E20;
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
            color: white;
        }
        
        /* Inputs */
        [data-testid="stFileUploader"] {
            background-color: #F8F9FA;
            border: 1px dashed #CED4DA;
            border-radius: 8px;
            padding: 10px;
        }
        
        hr {
            margin-top: 1em;
            margin-bottom: 1em;
            border: 0;
            border-top: 1px solid #E9ECEF;
        }
    </style>
    """, unsafe_allow_html=True)

def config_matplotlib():
    """Configura o tema claro globalmente para gráficos."""
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update({
        "axes.facecolor": "#FFFFFF",
        "figure.facecolor": "#FFFFFF",
        "text.color": "#333333",
        "axes.labelcolor": "#333333",
        "xtick.color": "#333333",
        "ytick.color": "#333333",
        "grid.color": "#E9ECEF"
    })