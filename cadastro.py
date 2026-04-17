import streamlit as st

# ==========================================
# 1. CONFIGURAÇÕES GLOBAIS
# ==========================================
st.set_page_config(page_title="Boi Gene - Sistema Integrado", layout="wide")

# Injeção de CSS global para manter o layout limpo e estilizar inputs
st.markdown("""
    <style>
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
        margin-top: 0 !important;
    }
    header {
        visibility: hidden !important; 
    }
    div[data-baseweb="input"] > div, div[data-baseweb="select"] > div {
        background-color: #d1d5db !important; 
        border: 1px solid #9ca3af !important;
    }
    div[data-baseweb="input"] input, div[data-baseweb="select"] div {
        color: #000000 !important;
        font-weight: 500 !important;
    }
    </style>
""", unsafe_allow_html=True)

def main():
    st.sidebar.title("🧬 Boi Gene")
    st.sidebar.subheader("Menu de Navegação")
    
    # Agrupamento das opções
    opcoes_menu = [
        "1. Cadastros Base (Tabelas de Apoio)",
        "2. Cadastros Principais (Dados de Campo)"
    ]
    
    escolha = st.sidebar.radio("Selecione o Módulo:", opcoes_menu)
    st.sidebar.divider()

    # Roteamento
    if escolha == opcoes_menu[0]:
        import cadastro_base
        cadastro_base.render_page()
    elif escolha == opcoes_menu[1]:
        import cadastro_principal
        cadastro_principal.render_page()

if __name__ == "__main__":
    main()