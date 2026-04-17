"""
Módulo Principal - BOI GENE Pro | Interface e Orquestração Integrada
"""

import streamlit as st
import pandas as pd
import os
import importlib

# Tenta importar o módulo de estilos (se existir)
try:
    import styles
except ImportError:
    pass

# --- Importação Dinâmica dos Módulos Externos (Processamento) ---
try: import gera_itu; importlib.reload(gera_itu)
except ImportError: pass

try: import tratamento_dados; importlib.reload(tratamento_dados)
except ImportError: pass

try: import qc_dados; importlib.reload(qc_dados)
except ImportError: pass

try: import renumf90; importlib.reload(renumf90)
except ImportError: pass

try: import airemlf90; importlib.reload(airemlf90)
except ImportError: pass

# --- Importação do módulo de Predição ---
try: import prediz_deps; importlib.reload(prediz_deps)
except ImportError: pass

# --- NOVO: Importação do módulo de Dashboard de DEPs ---
try: import dashboard_deps; importlib.reload(dashboard_deps)
except ImportError: pass

# --- Importação Dinâmica dos Módulos Externos (Cadastro e Exportação) ---
try: import cadastro_base; importlib.reload(cadastro_base)
except ImportError: pass

try: import cadastro_principal; importlib.reload(cadastro_principal)
except ImportError: pass

try: import exporta_dados; importlib.reload(exporta_dados)
except ImportError: pass

# ==============================================================================
# --- CONFIGURAÇÃO GLOBAL DA PÁGINA ---
# ==============================================================================
st.set_page_config(
    page_title="BoiGene Pro | Gestão e Genética",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Injeção de CSS global (Merge do BoiGene original com o layout do Cadastro)
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

try:
    styles.apply_custom_css()
    styles.config_matplotlib()
except NameError:
    pass 

# ==============================================================================
# --- GESTÃO DE ESTADO (SESSION STATE) ---
# ==============================================================================

# Estados Originais
if 'dados_processados' not in st.session_state: st.session_state.dados_processados = None
if 'dados_qc' not in st.session_state: st.session_state.dados_qc = None
if 'dados_renum' not in st.session_state: st.session_state.dados_renum = None
if 'dados_aireml' not in st.session_state: st.session_state.dados_aireml = None

# Estados do Novo Gerenciador de Workspace (Persistência em Disco)
if 'nome_projeto' not in st.session_state: st.session_state.nome_projeto = None
if 'workspace_dir' not in st.session_state: st.session_state.workspace_dir = None

# ==============================================================================
# --- MENU LATERAL E ROTEAMENTO PRINCIPAL ---
# ==============================================================================

logo_path = os.path.join("grafic_image", "logo boigene3.jpg") 
if os.path.exists(logo_path):
    st.sidebar.image(logo_path, use_container_width=True)
else:
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2990/2990399.png", caption="BoiGene Pro")

st.sidebar.title("🧬 BoiGene Pro")

# --- SELETOR DE ÁREA PRINCIPAL ---
area_sistema = st.sidebar.selectbox(
    "Selecione a Área do Sistema:",
    ["📋 Gestão de Cadastros", "🚀 Preparação e Pipelines (Dados)"]
)

st.sidebar.divider()

# ==============================================================================
# --- ÁREA 1: GESTÃO DE CADASTROS ---
# ==============================================================================
if area_sistema == "📋 Gestão de Cadastros":
    st.sidebar.subheader("Módulos de Cadastro")
    
    opcoes_cadastro = [
        "1. Cadastros Base (Tabelas de Apoio)",
        "2. Cadastros Principais (Dados de Campo)",
        "3. 📤 Exportação de Dados"
    ]
    escolha_cadastro = st.sidebar.radio("Navegação:", opcoes_cadastro)

    if escolha_cadastro == opcoes_cadastro[0]:
        if 'cadastro_base' in globals():
            cadastro_base.render_page()
        else:
            st.warning("O módulo cadastro_base.py não foi encontrado. Verifique o diretório.")
            
    elif escolha_cadastro == opcoes_cadastro[1]:
        if 'cadastro_principal' in globals():
            cadastro_principal.render_page()
        else:
            st.warning("O módulo cadastro_principal.py não foi encontrado. Verifique o diretório.")
            
    elif escolha_cadastro == opcoes_cadastro[2]:
        if 'exporta_dados' in globals():
            exporta_dados.main()
        else:
            st.warning("O módulo exporta_dados.py não foi encontrado. Verifique o diretório.")

# ==============================================================================
# --- ÁREA 2: PREPARAÇÃO E PIPELINES DE DADOS ---
# ==============================================================================
elif area_sistema == "🚀 Preparação e Pipelines (Dados)":
    st.sidebar.subheader("Fluxo de Processamento")
    
    menu_options_dados = [
        "1. 🌡️ ..01 Gera ITU",    
        "2. 📤 02 Tratamento Dados",
        "3. 🧬 03 Qualidade Genótipo (PREGSF90)",
        "4. 📁 04 Preparação Dados (RENUMF90)",
        "5. 📈 05 Cálculo Variâncias (AIREMLF90)",
        "6. 🐂 06 Predição de DEPs (BLUPF90)",
        "7. 📊 07 Dashboard de DEPs" 
    ]
    selection_dados = st.sidebar.radio("Selecione a Etapa:", menu_options_dados)

    # ==========================================================================
    # --- GERENCIADOR DE WORKSPACE E LIMPEZA (CONTROLE DE ESTADO) ---
    # ==========================================================================
    st.sidebar.divider()
    st.sidebar.subheader("📂 Gestão de Projeto (Workspace)")
    
    if not st.session_state.nome_projeto:
        st.sidebar.info("Nenhum projeto ativo. Crie ou carregue um projeto para iniciar o rastreio no disco.")
        
        # --- Lógica adicionada para listar pastas de projetos existentes ---
        diretorio_base_projetos = r"C:\boigene_data"
        projetos_existentes = []
        
        if os.path.exists(diretorio_base_projetos):
            projetos_existentes = [
                d for d in os.listdir(diretorio_base_projetos) 
                if os.path.isdir(os.path.join(diretorio_base_projetos, d))
            ]
            
        opcoes_projeto = ["+ Criar Novo Projeto"] + sorted(projetos_existentes)
        projeto_selecionado = st.sidebar.selectbox("Selecione ou Crie um Projeto:", opcoes_projeto)
        
        if projeto_selecionado == "+ Criar Novo Projeto":
            nome_input = st.sidebar.text_input("Nome da Nova Avaliação / Projeto:")
        else:
            nome_input = projeto_selecionado

        if st.sidebar.button("✔️ Iniciar Projeto", use_container_width=True):
            if nome_input and nome_input.strip():
                st.session_state.nome_projeto = nome_input.strip()
                # Força a criação na raiz C:\boigene_data caso seja novo
                caminho_base = os.path.join(diretorio_base_projetos, st.session_state.nome_projeto)
                os.makedirs(caminho_base, exist_ok=True)
                st.session_state.workspace_dir = caminho_base
                st.rerun()
            else:
                st.sidebar.error("Por favor, digite ou selecione um nome válido.")
    else:
        st.sidebar.success(f"📌 Projeto Ativo:\n**{st.session_state.nome_projeto}**")
        st.sidebar.caption(f"💾 Salvo em: `{st.session_state.workspace_dir}`")
        
        # Botão de segurança dupla para limpar o projeto e recomeçar
        with st.sidebar.expander("⚠️ Encerrar / Novo Projeto"):
            st.warning("Isso limpará a memória atual do sistema. Os arquivos físicos gerados até o momento continuarão salvos no HD da máquina.")
            if st.button("🚨 Confirmar Limpeza", type="primary", use_container_width=True):
                # Limpa chaves vitais da memória para forçar o reinício seguro
                chaves_para_limpar = [
                    'nome_projeto', 'workspace_dir', 'dados_processados', 'dados_qc', 
                    'dados_renum', 'dados_aireml', 'itu_resultado', 'itu_falhas', 'itu_form_submitted'
                ]
                for chave in chaves_para_limpar:
                    if chave in st.session_state:
                        del st.session_state[chave]
                st.rerun()

    st.sidebar.divider()

    # Limpeza de memória para dados voláteis (ITU) caso o usuário troque de tela
    if selection_dados != "1. 🌡️ ..01 Gera ITU":
        for key in ['itu_resultado', 'itu_falhas', 'itu_form_submitted']:
            if key in st.session_state: del st.session_state[key]

    # ==========================================================================
    # --- DESPACHO DE TELAS E GUARDRAILS (VALIDAÇÃO DE BURACOS) ---
    # ==========================================================================
    if not st.session_state.nome_projeto:
        st.warning("⚠️ **Atenção:** Você precisa iniciar um Projeto no menu lateral (📂 Gestão de Projeto) antes de acessar as ferramentas do Pipeline.")
    else:
        # --- Lógica de Proteção de Etapas (Guardrails) ---
        dependencias_pipeline = {
            "1. 🌡️ ..01 Gera ITU": [],
            "2. 📤 02 Tratamento Dados": [], # Portas de entrada
            "3. 🧬 03 Qualidade Genótipo (PREGSF90)": ["genotipos_tratado.csv", "pedigree_tratado.csv"],
            "4. 📁 04 Preparação Dados (RENUMF90)": ["fenotipos_tratados.csv", "genotipos_qc_final.csv", "pedigree_qc_final.csv"],
            "5. 📈 05 Cálculo Variâncias (AIREMLF90)": ["Dataset_RENUMF90_Pronto.zip"],
            "6. 🐂 06 Predição de DEPs (BLUPF90)": ["Variancias_Bifurcadas_Pronto.zip", "genotipos_qc_final.csv"], 
            "7. 📊 07 Dashboard de DEPs": ["Predicoes_GEBVs_Finais_Pronto.zip", "Variancias_Bifurcadas_Pronto.zip"]
        }

        arquivos_necessarios = dependencias_pipeline.get(selection_dados, [])
        arquivos_faltantes = []
        
        for arquivo in arquivos_necessarios:
            caminho_completo = os.path.join(st.session_state.workspace_dir, arquivo)
            if not os.path.exists(caminho_completo):
                arquivos_faltantes.append(arquivo)

        # Se houver um "buraco", bloqueia a tela imediatamente e NÃO RODA o arquivo .py
        if arquivos_faltantes:
            st.error("⚠️ **Bloqueio de Segurança: Etapa(s) Anterior(es) Incompleta(s)**")
            st.warning("Para acessar esta etapa, o sistema precisa ler os seguintes arquivos gerados nas etapas anteriores:\n\n" + 
                       "\n".join([f"- `{f}`" for f in arquivos_faltantes]))
            st.info("💡 **Ação Necessária:** Retorne no menu lateral e conclua as etapas pendentes para garantir a integridade dos dados.")
            st.stop() # <-- MATA A RENDERIZAÇÃO AQUI. O módulo abaixo nunca é chamado.

        # --- Despacho Seguro (Só executa se passar pelo Guardrail acima) ---
        if selection_dados == "1. 🌡️ ..01 Gera ITU":
            if 'gera_itu' in globals(): gera_itu.render_itu_module()
            else: st.warning("O módulo gera_itu.py não foi encontrado.")

        elif selection_dados == "2. 📤 02 Tratamento Dados":
            if 'tratamento_dados' in globals(): tratamento_dados.render_tratamento_module()
            else: st.warning("O módulo tratamento_dados.py não foi encontrado.")

        elif selection_dados == "3. 🧬 03 Qualidade Genótipo (PREGSF90)":
            if 'qc_dados' in globals(): qc_dados.render_qc_module()
            else: st.warning("O módulo qc_dados.py não foi encontrado.")

        elif selection_dados == "4. 📁 04 Preparação Dados (RENUMF90)":
            if 'renumf90' in globals(): renumf90.render_renumf90_module()
            else: st.warning("O módulo renumf90.py não foi encontrado.")

        elif selection_dados == "5. 📈 05 Cálculo Variâncias (AIREMLF90)":
            if 'airemlf90' in globals(): airemlf90.render_variance_module()
            else: st.warning("O módulo airemlf90.py não foi encontrado.")

        elif selection_dados == "6. 🐂 06 Predição de DEPs (BLUPF90)":
            if 'prediz_deps' in globals(): prediz_deps.render_prediction_module()
            else: st.warning("O módulo prediz_deps.py não foi encontrado. Verifique o diretório.")
            
        elif selection_dados == "7. 📊 07 Dashboard de DEPs":
            if 'dashboard_deps' in globals(): dashboard_deps.render_dashboard_module()
            else: st.warning("O módulo dashboard_deps.py não foi encontrado. Verifique o diretório.")