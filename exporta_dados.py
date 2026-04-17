import streamlit as st
import sqlite3
import pandas as pd
import os

# Configuração da página
st.set_page_config(page_title="Boi Gene - Exportação de Dados", layout="wide")

# NOVO CAMINHO DO BANCO DE DADOS
DB_PATH = r"c:/boigene/bd/boigene_db.db"

# Ordem e nomes exatos das colunas com base nos CSVs de referência
COLUNAS_REF = {
    "ambiente": ["ID_Animal", "Fazenda", "Estacao", "Lote_Manejo", "Regime_Alim", "Tipo_Pastagem", "Localidade_Bloco", "Data_Coleta_Pesagem", "Piquete"],
    "fenotipos": ["ID_Animal", "GC", "PN_kg", "PD_kg", "PS_kg", "GPD_g-dia", "PE_cm", "AOL_cm2", "EGS_mm", "MAR_%", "CAR_kg-dia", "PREC_SEX", "IPP_dias", "PROB_3P_%", "STAY_%"],
    "genotipos": ["ID_Animal", "Sequencia_SNP"],
    "pedigree": ["ID_Animal", "ID_Pai", "ID_Mae", "Sexo", "Geracao", "Raca", "Data_Nascimento", "Categoria"],
    "pesos_economicos": ["id_peso", "descricao", "nome_peso", "valor_estimado"]
}

@st.cache_resource
def get_connection():
    if not os.path.exists(DB_PATH):
        # Aviso na tela caso o BD não seja encontrado
        st.error(f"Banco de dados não encontrado no caminho: {DB_PATH}")
        return None
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def carregar_dados(conn):
    """Extrai os dados das tabelas reconstruindo os valores dos cadastros base (Views)"""
    
    # Query modificada para buscar a descrição da Fazenda e do Piquete
    query_amb = """
        SELECT 
            a.id_animal as ID_Animal,
            cf.descricao as Fazenda,
            ce.descricao as Estacao,
            clm.descricao as Lote_Manejo,
            cra.descricao as Regime_Alim,
            cp.descricao as Tipo_Pastagem,
            cl.descricao as Localidade_Bloco,
            a.Data_Coleta_Pesagem as Data_Coleta_Pesagem,
            cpiq.descricao as Piquete
        FROM ambiente a
        LEFT JOIN cadastro_fazenda cf ON a.id_fazenda = cf.id_fazenda
        LEFT JOIN cadastro_estacao ce ON a.id_estacao = ce.id_estacao
        LEFT JOIN cadastro_lote_manejo clm ON a.id_lote = clm.id_lote
        LEFT JOIN cadastro_regime_alim cra ON a.id_regime = cra.id_regime
        LEFT JOIN cadastro_pastagem cp ON a.id_pastagem = cp.id_pastagem
        LEFT JOIN cadastro_localidade cl ON a.id_localidade = cl.id_localidade
        LEFT JOIN cadastro_piquete cpiq ON a.id_piquete = cpiq.id_piquete
    """
    df_amb = pd.read_sql_query(query_amb, conn)

    query_fen = """
        SELECT 
            id_animal as ID_Animal, GC, PN_kg, PD_kg, PS_kg, "GPD_g-dia", 
            PE_cm, AOL_cm2, EGS_mm, "MAR_%", "CAR_kg-dia", PREC_SEX, 
            IPP_dias, "PROB_3P_%", "STAY_%" 
        FROM fenotipos
    """
    df_fen = pd.read_sql_query(query_fen, conn)

    df_gen = pd.read_sql_query("SELECT id_animal as ID_Animal, Sequencia_SNP FROM genotipos", conn)

    query_ped = """
        SELECT 
            p.id_animal as ID_Animal, p.id_pai as ID_Pai, p.id_mae as ID_Mae,
            cs.descricao as Sexo, p.Geracao, cr.descricao as Raca, 
            p.Data_Nascimento, cc.descricao as Categoria
        FROM pedigree p
        LEFT JOIN cadastro_sexo cs ON p.id_sexo = cs.id_sexo
        LEFT JOIN cadastro_raca cr ON p.id_raca = cr.id_raca
        LEFT JOIN cadastro_categoria cc ON p.id_categoria = cc.id_categoria
    """
    df_ped = pd.read_sql_query(query_ped, conn)

    df_pesos = pd.read_sql_query("SELECT id_peso, descricao, nome_peso, valor_estimado FROM pesos_economicos", conn)

    return {
        "ambiente": df_amb,
        "fenotipos": df_fen,
        "genotipos": df_gen,
        "pedigree": df_ped,
        "pesos_economicos": df_pesos
    }

def carregar_cadastros_base(conn):
    """Carrega as tabelas de domínio para preencher os filtros com textos amigáveis"""
    cadastros = {}
    cadastros['fazenda'] = pd.read_sql_query("SELECT id_fazenda, descricao FROM cadastro_fazenda", conn)
    cadastros['piquete'] = pd.read_sql_query("SELECT id_piquete, descricao FROM cadastro_piquete", conn)
    return cadastros

def main():
    st.title("🧬 Boi Gene - Exportação de Dados")
    st.markdown("Filtre os dados utilizando o cadastro base e exporte em CSV (separador `;`).")

    conn = get_connection()
    if not conn:
        return

    with st.spinner("Carregando banco de dados..."):
        dados_db = carregar_dados(conn)
        cadastros = carregar_cadastros_base(conn)

    # A interface de opções do multiselect ainda utiliza as descrições dos cadastros base
    ops_fazenda = cadastros['fazenda']['descricao'].dropna().unique().tolist()
    ops_piquete = cadastros['piquete']['descricao'].dropna().unique().tolist()
    ops_localidade = dados_db['ambiente']['Localidade_Bloco'].dropna().unique().tolist()
    ops_data = dados_db['ambiente']['Data_Coleta_Pesagem'].dropna().unique().tolist()
    ops_gc = dados_db['fenotipos']['GC'].dropna().unique().tolist()
    
    todos_animais = list(set(dados_db['ambiente']['ID_Animal'].tolist() + dados_db['fenotipos']['ID_Animal'].tolist()))

    # --- INICIALIZAR MEMÓRIA DO STREAMLIT (SESSION STATE) ---
    if 'tabelas_processadas' not in st.session_state:
        st.session_state.tabelas_processadas = None

    # --- SEÇÃO DE FILTROS ---
    st.sidebar.header("Filtros de Exportação")
    st.sidebar.markdown("Deixe em branco para ignorar e exportar tudo.")

    filtro_id = st.sidebar.multiselect("ID Animal", options=sorted(todos_animais))
    filtro_fazenda = st.sidebar.multiselect("Fazenda", options=sorted(ops_fazenda))
    filtro_bloco = st.sidebar.multiselect("Localidade / Bloco", options=sorted(ops_localidade))
    filtro_data = st.sidebar.multiselect("Data Coleta / Pesagem", options=sorted(ops_data))
    filtro_piquete = st.sidebar.multiselect("Piquete", options=sorted(ops_piquete))
    filtro_gc = st.sidebar.multiselect("Grupo de Contemporâneos (GC)", options=sorted(ops_gc))

    if st.sidebar.button("Aplicar Filtros e Gerar Exportações", type="primary"):
        # Iniciar com todos os IDs
        ids_validos = set(todos_animais)

        if filtro_id or filtro_fazenda or filtro_bloco or filtro_data or filtro_piquete or filtro_gc:
            
            # Filtros da tabela Ambiente
            df_amb_f = dados_db['ambiente'].copy()
            if filtro_id:
                df_amb_f = df_amb_f[df_amb_f['ID_Animal'].isin(filtro_id)]
            if filtro_fazenda:
                # O DataFrame já possui a string com a descrição, filtramos direto
                df_amb_f = df_amb_f[df_amb_f['Fazenda'].isin(filtro_fazenda)]
            if filtro_bloco:
                df_amb_f = df_amb_f[df_amb_f['Localidade_Bloco'].isin(filtro_bloco)]
            if filtro_data:
                df_amb_f = df_amb_f[df_amb_f['Data_Coleta_Pesagem'].isin(filtro_data)]
            if filtro_piquete:
                # O DataFrame já possui a string com a descrição, filtramos direto
                df_amb_f = df_amb_f[df_amb_f['Piquete'].isin(filtro_piquete)]
            
            ids_amb = set(df_amb_f['ID_Animal'].tolist())

            # Filtros da tabela Fenótipos
            df_fen_f = dados_db['fenotipos'].copy()
            if filtro_gc:
                df_fen_f = df_fen_f[df_fen_f['GC'].isin(filtro_gc)]
                ids_fen = set(df_fen_f['ID_Animal'].tolist())
            else:
                ids_fen = set(dados_db['fenotipos']['ID_Animal'].tolist())

            # Intersecção dos IDs válidos
            ids_validos = ids_amb.intersection(ids_fen)

            if not ids_validos:
                st.warning("Nenhum animal encontrado com a combinação de filtros selecionada.")
                st.session_state.tabelas_processadas = None
            else:
                # Gerar os dados finais e salvar no state
                tabelas_finais = {}
                for nome_tabela, colunas_desejadas in COLUNAS_REF.items():
                    df_export = dados_db[nome_tabela].copy()
                    
                    if nome_tabela != "pesos_economicos" and ids_validos is not None:
                        if 'ID_Animal' in df_export.columns:
                            df_export = df_export[df_export['ID_Animal'].isin(ids_validos)]

                    # Ajustar colunas
                    for col in colunas_desejadas:
                        if col not in df_export.columns:
                            df_export[col] = None 
                    df_export = df_export[colunas_desejadas]
                    
                    tabelas_finais[nome_tabela] = df_export

                st.session_state.tabelas_processadas = tabelas_finais

        else:
            # Caso não tenha nenhum filtro aplicado, exporta tudo diretamente
            tabelas_finais = {}
            for nome_tabela, colunas_desejadas in COLUNAS_REF.items():
                df_export = dados_db[nome_tabela].copy()
                for col in colunas_desejadas:
                    if col not in df_export.columns:
                        df_export[col] = None 
                df_export = df_export[colunas_desejadas]
                tabelas_finais[nome_tabela] = df_export

            st.session_state.tabelas_processadas = tabelas_finais


    # --- RENDERIZAR RESULTADOS (Fora do bloco do botão, baseado na Memória da Sessão) ---
    if st.session_state.tabelas_processadas is not None:
        st.subheader("Pré-visualização e Exportação")
        tabs = st.tabs(list(COLUNAS_REF.keys()))

        for i, (nome_tabela, df_export) in enumerate(st.session_state.tabelas_processadas.items()):
            with tabs[i]:
                st.write(f"**Registros encontrados:** {len(df_export)}")
                st.dataframe(df_export.head(50))

                # Converter para CSV
                csv = df_export.to_csv(index=False, sep=';', encoding='utf-8')
                
                # Botão de download (mesmo quando clicado, a tabela não sumirá)
                st.download_button(
                    label=f"⬇️ Baixar {nome_tabela}.csv",
                    data=csv,
                    file_name=f"{nome_tabela}.csv",
                    mime="text/csv"
                )

if __name__ == "__main__":
    main()