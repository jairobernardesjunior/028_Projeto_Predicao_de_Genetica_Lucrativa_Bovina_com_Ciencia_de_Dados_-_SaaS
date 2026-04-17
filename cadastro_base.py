import streamlit as st
import pandas as pd
import sqlite3
import os
import time

DB_DIR = r"C:\boigene\bd"
DB_PATH = os.path.join(DB_DIR, "boigene_db.db")
os.makedirs(DB_DIR, exist_ok=True)

# Adicionado o esquema para Pesos Econômicos com a estrutura correta de colunas
SCHEMAS = {
    "Animais": {"title": "🐄 Manutenção do Cadastro de Animais", "table": "cadastro_animais", "key": "id_animal", "cols": ["id_animal", "descricao_animal", "anulado"], "help_text": "Exemplos: Touro Bandido, Matriz 1024, Bezerro 2025-001"},
    "Fazenda": {"title": "🏡 Manutenção de Propriedades (Fazendas)", "table": "cadastro_fazenda", "key": "id_fazenda", "cols": ["id_fazenda", "descricao", "anulado"], "help_text": "Exemplos: Fazenda Santa Maria, Rancho Fundo, Unidade Uberlândia"},
    "Estacao": {"title": "🌦️ Manutenção de Estações do Ano", "table": "cadastro_estacao", "key": "id_estacao", "cols": ["id_estacao", "descricao", "anulado"], "help_text": "Exemplos: Primavera, Verão, Outono, Inverno, Águas, Seca"},
    "Lote de Manejo": {"title": "🏷️ Manutenção de Lotes de Manejo", "table": "cadastro_lote_manejo", "key": "id_lote", "cols": ["id_lote", "descricao", "anulado"], "help_text": "Exemplos: Confinamento, Pasto 08, Desmama 2024"},
    "Regime Alimentar": {"title": "🌾 Manutenção de Regimes Alimentares", "table": "cadastro_regime_alim", "key": "id_regime", "cols": ["id_regime", "descricao", "anulado"], "help_text": "Exemplos: Pasto, Pasto + Suplemento, Confinamento"},
    "Tipo de Pastagem": {"title": "🌱 Manutenção de Tipos de Pastagem", "table": "cadastro_pastagem", "key": "id_pastagem", "cols": ["id_pastagem", "descricao", "anulado"], "help_text": "Exemplos: Braquiária, Mombaça, Panicum, Dieta Total"},
    "Localidade / Bloco": {"title": "📍 Manutenção de Localidades e Blocos", "table": "cadastro_localidade", "key": "id_localidade", "cols": ["id_localidade", "descricao", "anulado"], "help_text": "Exemplos: Setor_1A, Retiro Sul, Baixada Fértil"},
    "Piquete": {"title": "🚧 Manutenção de Piquetes", "table": "cadastro_piquete", "key": "id_piquete", "cols": ["id_piquete", "descricao", "anulado"], "help_text": "Exemplos: 1, 2, 42, Piquete Maternidade"},
    "Sexo": {"title": "⚧️ Manutenção de Sexo Biológico", "table": "cadastro_sexo", "key": "id_sexo", "cols": ["id_sexo", "descricao", "anulado"], "help_text": "Exemplos: M, F, Macho, Fêmea"},
    "Raça": {"title": "🧬 Manutenção de Raças", "table": "cadastro_raca", "key": "id_raca", "cols": ["id_raca", "descricao", "anulado"], "help_text": "Exemplos: Nelore, Angus, Brahman, Cruzamento Industrial"},
    "Categoria": {"title": "📋 Manutenção de Categorias de Rebanho", "table": "cadastro_categoria", "key": "id_categoria", "cols": ["id_categoria", "descricao", "anulado"], "help_text": "Exemplos: Animal Avaliado, Matriz Fundadora, Touro Fundador"},
    "Pesos Econômicos": {"title": "⚖️ Manutenção de Pesos Econômicos", "table": "pesos_economicos", "key": "id_peso", "cols": ["id_peso", "descricao", "nome_peso", "valor_estimado", "anulado"], "help_text": "Definição do peso econômico das características (ex: PD_kg, STAY_%)"}
}

def get_db_connection(timeout=10.0):
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    for schema_key, schema_info in SCHEMAS.items():
        table = schema_info["table"]
        key_col = schema_info["key"]
        cols = schema_info["cols"]
        
        col_defs = []
        for col in cols:
            if col == key_col:
                col_defs.append(f"{col} INTEGER PRIMARY KEY")
            elif col == "anulado":
                col_defs.append(f"{col} INTEGER DEFAULT 0")
            elif col == "valor_estimado": # Tratamento específico para campos numéricos
                 col_defs.append(f"{col} REAL")
            else:
                col_defs.append(f"{col} TEXT")
                
        sql = f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(col_defs)})"
        cursor.execute(sql)
    conn.commit()
    conn.close()

@st.cache_data(show_spinner=False, ttl=3600)
def load_data(tabela_selecionada):
    table_name = SCHEMAS[tabela_selecionada]["table"]
    cols = SCHEMAS[tabela_selecionada]["cols"]
    
    conn = get_db_connection()
    try:
        df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
        if not df.empty and 'anulado' in df.columns:
            df['anulado'] = df['anulado'].astype(bool)
    except Exception:
        df = pd.DataFrame(columns=cols)
    finally:
        conn.close()
    return df

def save_record(tabela_selecionada, input_key, input_values, anulado, is_update):
    table_name = SCHEMAS[tabela_selecionada]["table"]
    key_col = SCHEMAS[tabela_selecionada]["key"]
    
    # Preparando o dicionário final para salvar
    registro = {key_col: input_key}
    registro.update(input_values)
    registro["anulado"] = 1 if anulado else 0
    
    max_retries = 3
    retry_delay = 0.5

    for attempt in range(max_retries):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Garantir que a ordem das colunas no UPDATE/INSERT corresponda aos valores
            colunas_para_salvar = [k for k in registro.keys() if k != key_col]
            
            if is_update:
                campos_set = [f"{k} = ?" for k in colunas_para_salvar]
                valores = [registro[k] for k in colunas_para_salvar]
                valores.append(input_key) # O ID vai por último no WHERE
                
                sql = f"UPDATE {table_name} SET {', '.join(campos_set)} WHERE {key_col} = ?"
                cursor.execute(sql, valores)
            else:
                todas_colunas = [key_col] + colunas_para_salvar
                placeholders = ", ".join(["?"] * len(todas_colunas))
                valores = [registro[k] for k in todas_colunas]
                
                sql = f"INSERT INTO {table_name} ({', '.join(todas_colunas)}) VALUES ({placeholders})"
                cursor.execute(sql, valores)
                
            conn.commit()
            load_data.clear() 
            return True, ""
            
        except sqlite3.IntegrityError as e:
            error_msg = str(e).lower()
            if "unique constraint" in error_msg or "primary key" in error_msg:
                return False, f"Violação de chave: O código {input_key} já está cadastrado ou em uso."
            elif "foreign key constraint" in error_msg:
                return False, "Violação de integridade referencial: Este registro não pode ser alterado pois está vinculado a outras tabelas."
            else:
                return False, f"Erro de integridade nos dados: {e}"
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                time.sleep(retry_delay)
                continue
            return False, f"Erro operacional no banco: {e}"
        except Exception as e:
            return False, f"Erro inesperado: {e}"
        finally:
            if 'conn' in locals():
                conn.close()
                
    return False, "O banco de dados está bloqueado por outra operação. Tente novamente em instantes."

def render_page():
    # Inicializa o BD garantindo que todas as tabelas existam
    init_db()
    
    tabela_selecionada = st.sidebar.selectbox("Selecione o Cadastro Base:", list(SCHEMAS.keys()))
    schema_atual = SCHEMAS[tabela_selecionada]
    
    st.title(schema_atual["title"])

    df_atual = load_data(tabela_selecionada)
    key_col = schema_atual["key"]
    tooltip_text = schema_atual["help_text"]

    st.markdown("### 📋 Registros Atuais")
    if not df_atual.empty:
        st.dataframe(df_atual, width='stretch', hide_index=True, height=210)
    else:
        st.info("Nenhum registro encontrado no banco de dados. Utilize o formulário abaixo para incluir.")

    st.divider()
    st.markdown("### 🛠️ Inclusão / Alteração")

    existe = False
    
    # Campo de Chave Primária (sempre presente)
    input_key = st.number_input(f"Chave Numérica ({key_col})", min_value=0, step=1, format="%d")

    # Verifica se o registro já existe para carregar os dados
    df_filtrado = df_atual[df_atual[key_col] == input_key]
    existe = not df_filtrado.empty

    # Dicionário para armazenar os valores dos inputs dinamicamente
    input_values = {}
    val_anulado = False

    if existe:
        st.info(f"🔵 Editando registro existente: **{input_key}**")
        registro_existente = df_filtrado.iloc[0]
        val_anulado = bool(registro_existente.get("anulado", False))
    else:
        st.success("🟢 Criando novo registro")

    # Geração dinâmica dos campos de formulário baseada nas colunas do schema
    # Ignoramos a chave primária e o campo anulado, pois são tratados separadamente
    colunas_form = [c for c in schema_atual["cols"] if c not in [key_col, "anulado"]]
    
    for col_name in colunas_form:
        # Prepara o valor inicial (vazio para novo, ou o valor do BD se existir)
        val_inicial = ""
        if existe and col_name in registro_existente:
            val_inicial = registro_existente[col_name]
            # Trata nulos do pandas
            if pd.isna(val_inicial):
                 val_inicial = ""
                 
        # Tratamento específico para campos numéricos na tabela de Pesos
        if col_name == "valor_estimado":
            # Converte para float se existir, senão 0.0
            val_float = float(val_inicial) if val_inicial != "" else 0.0
            input_values[col_name] = st.number_input("Valor Estimado (R$)", value=val_float, step=0.01, format="%.2f")
        else:
            # Rótulos amigáveis baseados no nome da coluna
            label_display = "Descrição / Nome do Animal *" if col_name == "descricao_animal" else \
                            "Nome Técnico (ex: PD_kg) *" if col_name == "nome_peso" else \
                            "Descrição *" if col_name == "descricao" else col_name.capitalize() + " *"
                            
            # Garante que seja string para o text_input
            input_values[col_name] = st.text_input(label_display, value=str(val_inicial), help=tooltip_text)

    # Campo Anulado
    anulado = st.checkbox("🚫 Registro Anulado (Exclusão Lógica)", value=val_anulado)

    st.warning("⚠️ Revise os dados antes de confirmar.")
    confirmacao = st.checkbox("Confirmo a operação acima")

    submitted = st.button("💾 Salvar Registro", type="primary")
    msg_placeholder = st.empty()
    st.markdown("<br><br>", unsafe_allow_html=True)

    if submitted:
        # Validação básica: verificar se os campos texto não estão vazios
        campos_invalidos = []
        for k, v in input_values.items():
            if isinstance(v, str) and not v.strip():
                campos_invalidos.append(k)
                
        if campos_invalidos:
            nomes_campos = ", ".join(campos_invalidos)
            msg_placeholder.error(f"❌ O(s) campo(s) obrigatório(s) não pode(m) ficar em branco: {nomes_campos}")
        elif not confirmacao:
            msg_placeholder.error("❌ Por favor, marque a caixa 'Confirmo a operação acima' para prosseguir.")
        else:
            # Limpa espaços em branco das strings antes de salvar
            for k, v in input_values.items():
                 if isinstance(v, str):
                      input_values[k] = v.strip()
                      
            sucesso, erro_msg = save_record(tabela_selecionada, input_key, input_values, anulado, is_update=existe)
            
            if sucesso:
                if existe:
                    msg_placeholder.success(f"Registro {input_key} alterado com sucesso! Atualizando tela...")
                else:
                    msg_placeholder.success(f"Registro {input_key} incluído com sucesso! Atualizando tela...")
                time.sleep(1.5)
                st.rerun()
            else:
                msg_placeholder.error(f"❌ {erro_msg}")

if __name__ == "__main__":
    st.set_page_config(page_title="Cadastro Base", layout="wide")
    render_page()