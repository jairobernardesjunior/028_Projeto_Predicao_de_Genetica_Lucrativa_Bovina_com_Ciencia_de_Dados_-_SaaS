import streamlit as st
import pandas as pd
import sqlite3
import os
import time
import datetime
import re

DB_DIR = r"C:\boigene\bd"
DB_PATH = os.path.join(DB_DIR, "boigene_db.db")
os.makedirs(DB_DIR, exist_ok=True)

FK_MAPPING = {
    "id_animal": ("cadastro_animais", "id_animal", "descricao_animal"),
    "id_pai": ("cadastro_animais", "id_animal", "descricao_animal"),
    "id_mae": ("cadastro_animais", "id_animal", "descricao_animal"),
    "id_animal_phenotype": ("cadastro_animais", "id_animal", "descricao_animal"),
    "id_animal_genotype": ("cadastro_animais", "id_animal", "descricao_animal"),
    "id_fazenda": ("cadastro_fazenda", "id_fazenda", "descricao"),
    "id_estacao": ("cadastro_estacao", "id_estacao", "descricao"),
    "id_lote": ("cadastro_lote_manejo", "id_lote", "descricao"),
    "id_regime": ("cadastro_regime_alim", "id_regime", "descricao"),
    "id_pastagem": ("cadastro_pastagem", "id_pastagem", "descricao"),
    "id_localidade": ("cadastro_localidade", "id_localidade", "descricao"),
    "id_piquete": ("cadastro_piquete", "id_piquete", "descricao"),
    "id_categoria": ("cadastro_categoria", "id_categoria", "descricao"),
    "id_sexo": ("cadastro_sexo", "id_sexo", "descricao"),
    "id_raca": ("cadastro_raca", "id_raca", "descricao")
}

COL_TYPES = {
    "Data_Coleta_Pesagem": "TEXT", "Data_Nascimento": "TEXT", "GC": "TEXT", "Sequencia_SNP": "TEXT",
    "ITU_Media": "REAL", "ITU_DP": "REAL", "ITU_Max": "REAL",
    "PN_kg": "REAL", "PD_kg": "REAL", "PS_kg": "REAL", "GPD_g-dia": "REAL",
    "PE_cm": "REAL", "AOL_cm2": "REAL", "EGS_mm": "REAL", "MAR_%": "REAL",
    "CAR_kg-dia": "REAL", "PREC_SEX": "REAL", "IPP_dias": "REAL", "PROB_3P_%": "REAL", "STAY_%": "REAL",
    "Geracao": "INTEGER"
}

SCHEMAS = {
    "Ambiente": {
        "title": "🌦️ Manutenção de Ambiente",
        "table": "ambiente", 
        "keys": ["id_animal", "Data_Coleta_Pesagem"], 
        "cols": [
            "id_animal", "Data_Coleta_Pesagem", "id_fazenda", "id_piquete", 
            "ITU_Media", "ITU_DP", "ITU_Max", "id_estacao", "id_lote", 
            "id_regime", "id_pastagem", "id_localidade", "anulado"
        ]
    },
    "Pedigree": {
        "title": "🧬 Manutenção de Pedigree",
        "table": "pedigree", 
        "keys": ["id_animal"], 
        "cols": ["id_animal", "id_pai", "id_mae", "Geracao", "Data_Nascimento", 
        "id_sexo", "id_raca", "id_categoria", "anulado"]
    },
    "Fenótipos": {
        "title": "⚖️ Manutenção de Fenótipos",
        "table": "fenotipos", 
        "keys": ["id_animal"], 
        "cols": [
            "id_animal", "GC", "PN_kg", "PD_kg", "PS_kg", "GPD_g-dia", 
            "PE_cm", "AOL_cm2", "EGS_mm", "MAR_%", "CAR_kg-dia", "PREC_SEX", 
            "IPP_dias", "PROB_3P_%", "STAY_%", "anulado"
        ]
    },
    "Genótipos": {
        "title": "🔬 Manutenção de Genótipos",
        "table": "genotipos", 
        "keys": ["id_animal"], 
        "cols": ["id_animal", "Sequencia_SNP", "anulado"]
    },
    "Relação IDs": {
        "title": "🔗 Relação IDs (Fenótipo x Genótipo)",
        "table": "relacao_ids", 
        "keys": ["id_animal_phenotype"], 
        "cols": ["id_animal_phenotype", "id_animal_genotype", "anulado"]
    }
}

def get_db_connection(timeout=10.0):
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Recriação condicional das base tables para integridade
    tabelas_base = {
        "cadastro_animais": "id_animal INTEGER PRIMARY KEY, descricao_animal TEXT, anulado INTEGER DEFAULT 0",
        "cadastro_fazenda": "id_fazenda INTEGER PRIMARY KEY, descricao TEXT, anulado INTEGER DEFAULT 0",
        "cadastro_estacao": "id_estacao INTEGER PRIMARY KEY, descricao TEXT, anulado INTEGER DEFAULT 0",
        "cadastro_lote_manejo": "id_lote INTEGER PRIMARY KEY, descricao TEXT, anulado INTEGER DEFAULT 0",
        "cadastro_regime_alim": "id_regime INTEGER PRIMARY KEY, descricao TEXT, anulado INTEGER DEFAULT 0",
        "cadastro_pastagem": "id_pastagem INTEGER PRIMARY KEY, descricao TEXT, anulado INTEGER DEFAULT 0",
        "cadastro_localidade": "id_localidade INTEGER PRIMARY KEY, descricao TEXT, anulado INTEGER DEFAULT 0",
        "cadastro_piquete": "id_piquete INTEGER PRIMARY KEY, descricao TEXT, anulado INTEGER DEFAULT 0",
        "cadastro_sexo": "id_sexo INTEGER PRIMARY KEY, descricao TEXT, anulado INTEGER DEFAULT 0",
        "cadastro_raca": "id_raca INTEGER PRIMARY KEY, descricao TEXT, anulado INTEGER DEFAULT 0",
        "cadastro_categoria": "id_categoria INTEGER PRIMARY KEY, descricao TEXT, anulado INTEGER DEFAULT 0"
    }
    for tabela, colunas in tabelas_base.items():
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {tabela} ({colunas})")

    for schema_key, schema_info in SCHEMAS.items():
        table = schema_info["table"]
        keys = schema_info["keys"]
        cols = schema_info["cols"]
        
        col_defs = []
        for col in cols:
            col_quoted = f'"{col}"'
            if col == "anulado":
                col_defs.append(f"{col_quoted} INTEGER DEFAULT 0")
            elif COL_TYPES.get(col) == "TEXT" or col == "Data_Coleta_Pesagem":
                col_defs.append(f"{col_quoted} TEXT")
            elif COL_TYPES.get(col) == "REAL":
                col_defs.append(f"{col_quoted} REAL")
            else:
                col_defs.append(f"{col_quoted} INTEGER")
                
        keys_quoted = ', '.join([f'"{k}"' for k in keys])
        pk_sql = f"PRIMARY KEY ({keys_quoted})"
        
        all_defs = col_defs + [pk_sql]
        sql = f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(all_defs)})"
        cursor.execute(sql)
    conn.commit()
    conn.close()

def get_lookup_dict(col_name):
    if col_name not in FK_MAPPING: return {}
    table_name, id_col, desc_col = FK_MAPPING[col_name]
    conn = get_db_connection()
    try:
        query = f"SELECT {id_col}, {desc_col} FROM {table_name} WHERE anulado = 0 OR anulado IS NULL"
        df = pd.read_sql(query, conn)
        return {row[id_col]: f"{row[id_col]} - {row[desc_col]}" for _, row in df.iterrows()}
    except Exception:
        return {}
    finally:
        conn.close()

@st.cache_data(show_spinner=False, ttl=3600)
def load_data(tabela_selecionada):
    table_name = SCHEMAS[tabela_selecionada]["table"]
    cols = SCHEMAS[tabela_selecionada]["cols"]
    conn = get_db_connection()
    try:
        df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
        for col in cols:
            if col not in df.columns:
                df[col] = pd.NA
        if not df.empty and 'anulado' in df.columns:
            df['anulado'] = df['anulado'].astype(bool)
    except Exception:
        df = pd.DataFrame(columns=cols)
    finally:
        conn.close()
    return df

def save_record(tabela_selecionada, input_keys, input_values, anulado, is_update):
    table_name = SCHEMAS[tabela_selecionada]["table"]
    keys = SCHEMAS[tabela_selecionada]["keys"]
    
    registro = input_keys.copy()
    registro.update(input_values)
    registro["anulado"] = 1 if anulado else 0
    
    for attempt in range(3):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            if is_update:
                campos_set = [f'"{k}" = ?' for k in registro.keys() if k not in keys]
                valores = [registro[k] for k in registro.keys() if k not in keys]
                where_clause = " AND ".join([f'"{k}" = ?' for k in keys])
                valores.extend([input_keys[k] for k in keys])
                
                sql = f'UPDATE {table_name} SET {", ".join(campos_set)} WHERE {where_clause}'
                cursor.execute(sql, valores)
            else:
                colunas = ", ".join([f'"{k}"' for k in registro.keys()])
                placeholders = ", ".join(["?"] * len(registro))
                valores = list(registro.values())
                
                sql = f"INSERT INTO {table_name} ({colunas}) VALUES ({placeholders})"
                cursor.execute(sql, valores)
                
            conn.commit()
            load_data.clear() 
            return True, ""
        except sqlite3.IntegrityError as e:
            return False, f"Erro de integridade/violação de chave: {e}"
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                time.sleep(0.5)
                continue
            return False, f"Erro operacional: {e}"
        finally:
            if 'conn' in locals(): conn.close()
    return False, "Banco bloqueado."

def render_page():
    init_db()
    
    tabela_selecionada = st.sidebar.selectbox("Selecione a Tabela Principal:", list(SCHEMAS.keys()))
    st.title(SCHEMAS[tabela_selecionada]["title"])

    df_atual = load_data(tabela_selecionada)
    keys = SCHEMAS[tabela_selecionada]["keys"]
    cols = SCHEMAS[tabela_selecionada]["cols"]

    st.markdown("### 📋 Registros Atuais")
    selected_record = None

    if not df_atual.empty:
        df_display = df_atual.copy()
        for col in df_display.columns:
            if col in FK_MAPPING:
                lookup = get_lookup_dict(col)
                reverse_lookup = {str(v).split(" - ", 1)[1].strip().lower(): v for k, v in lookup.items() if " - " in str(v)}
                
                def format_fk(val):
                    if pd.isna(val): return ""
                    val_str = str(val).strip()
                    if val_str.lower() in ["nan", "<na>", "none", ""]: return ""
                    try:
                        num_id = int(float(val_str))
                        if num_id in lookup: return lookup[num_id]
                    except ValueError: pass
                    val_lower = val_str.lower()
                    if val_lower in reverse_lookup: return reverse_lookup[val_lower] 
                    return val_str
                    
                df_display[col] = df_display[col].apply(format_fk)
                
        selection_event = st.dataframe(
            df_display, width='stretch', hide_index=True, height=210,
            on_select="rerun", selection_mode="single-row", key=f"grid_{tabela_selecionada}"
        )
        current_selection = selection_event.selection.rows if hasattr(selection_event, 'selection') else []
        if current_selection: selected_record = df_atual.iloc[current_selection[0]]
    else:
        current_selection = []
        st.info("Nenhum registro encontrado no banco de dados.")

    st.divider()
    st.markdown("### 🛠️ Inclusão / Alteração")
    msg_placeholder = st.empty()

    col1, col2 = st.columns([1, 3])
    input_keys_dict = {}
    pk_suffix = f"row_{current_selection[0]}" if current_selection else "new"

    with col1:
        st.markdown("##### Chaves do Registro")
        k1 = keys[0]
        val_k1 = selected_record[k1] if selected_record is not None else None
        
        if k1 in FK_MAPPING:
            lookup_key = get_lookup_dict(k1)
            options_key = [""] + list(lookup_key.values())
            index_k1 = 0
            if pd.notna(val_k1):
                try:
                    val_k1_int = int(float(val_k1))
                    for i, opt in enumerate(options_key):
                        if opt.startswith(f"{val_k1_int} -") or opt == str(val_k1_int):
                            index_k1 = i; break
                except ValueError: pass
            
            selecao_k1 = st.selectbox(f"Registro Base ({k1}) *", options=options_key, index=index_k1, key=f"select_pk1_{tabela_selecionada}_{pk_suffix}")
            if selecao_k1:
                match_key = re.match(r"^(\d+)", selecao_k1)
                input_keys_dict[k1] = int(match_key.group(1)) if match_key else None
            else:
                input_keys_dict[k1] = None
        else:
            default_val_k1 = int(float(val_k1)) if pd.notna(val_k1) else 1
            input_keys_dict[k1] = st.number_input(f"Chave Numérica ({k1}) *", min_value=1, step=1, value=default_val_k1, format="%d", key=f"input_pk1_{tabela_selecionada}_{pk_suffix}")

        if len(keys) > 1:
            k2 = keys[1]
            default_date = datetime.date.today()
            if selected_record is not None:
                val_k2 = selected_record[k2]
                if pd.notna(val_k2) and str(val_k2).strip() != "":
                    try: default_date = datetime.datetime.strptime(str(val_k2)[:10], "%Y-%m-%d").date()
                    except ValueError: pass
            
            selecao_k2 = st.date_input(f"Data Coleta/Pesagem ({k2}) *", value=default_date, format="YYYY/MM/DD", key=f"select_pk2_{tabela_selecionada}_{pk_suffix}")
            input_keys_dict[k2] = selecao_k2.strftime("%Y-%m-%d") if selecao_k2 else None

    valid_keys = all(input_keys_dict.get(k) is not None for k in keys)
    key_suffix = "_".join([str(input_keys_dict.get(k, 'none')) for k in keys])

    if valid_keys:
        mask = pd.Series(True, index=df_atual.index)
        for k in keys: mask = mask & (df_atual[k] == input_keys_dict[k])
        existe = not df_atual[mask].empty

        with col1:
            if existe:
                st.info(f"🔵 Editando registro existente.")
                registro_existente = df_atual[mask].iloc[0]
                val_anulado = bool(registro_existente["anulado"])
            else:
                st.success("🟢 Criando novo registro.")
                val_anulado = False

        input_values = {}
        with col2:
            for col in cols:
                if col in keys or col == "anulado": continue
                
                label = col.replace("_", " ").title()
                val_default = registro_existente[col] if existe else None
                val_str = str(val_default).strip() if pd.notna(val_default) else ""
                if val_str.lower() in ["nan", "<na>", "none", ""]: val_str = ""
                
                if col in FK_MAPPING:
                    lookup = get_lookup_dict(col)
                    options = [""] + list(lookup.values())
                    default_index = 0
                    if val_str != "":
                        if val_str in options: default_index = options.index(val_str)
                        else:
                            match_id = re.match(r"^\s*(\d+)", val_str)
                            if match_id and lookup.get(int(match_id.group(1))) in options:
                                default_index = options.index(lookup.get(int(match_id.group(1))))
                            else:
                                for opt in options:
                                    if opt != "" and (val_str.lower() in opt.split(" - ", 1)[-1].strip().lower() or val_str.lower() == opt.split(" - ", 1)[-1].strip().lower()):
                                        default_index = options.index(opt); break
                            
                    selecao = st.selectbox(f"{label}", options=options, index=default_index, key=f"sel_{col}_{key_suffix}")
                    match = re.match(r"^(\d+)", selecao) if selecao else None
                    input_values[col] = int(match.group(1)) if match else None
                        
                elif COL_TYPES.get(col) == "TEXT":
                    if "Data" in col:
                        try:
                            default_date = datetime.datetime.strptime(val_str[:10], "%Y-%m-%d").date() if val_str != "" else None
                        except ValueError:
                            default_date = None
                        selecao_data = st.date_input(f"{label} (AAAA-MM-DD)", value=default_date, format="YYYY/MM/DD", key=f"date_{col}_{key_suffix}")
                        input_values[col] = selecao_data.strftime("%Y-%m-%d") if selecao_data else None
                    elif col == "Sequencia_SNP":
                        input_values[col] = st.text_area(f"{label}", value=val_str, height=100, key=f"area_{col}_{key_suffix}")
                    else:
                        input_values[col] = st.text_input(f"{label}", value=val_str, key=f"txt_{col}_{key_suffix}")
                        
                elif COL_TYPES.get(col) == "REAL":
                    try: val = float(val_str) if val_str != "" else 0.0
                    except: val = 0.0
                    input_values[col] = st.number_input(label, value=val, format="%.4f", key=f"num_{col}_{key_suffix}")
                else:
                    try: val = int(float(val_str)) if val_str != "" else 0
                    except: val = 0
                    input_values[col] = st.number_input(label, value=val, step=1, key=f"int_{col}_{key_suffix}")

        with col1:
            st.write("")
            anulado = st.checkbox("🚫 Registro Anulado (Inativar)", value=val_anulado, key=f"chk_anulado_{key_suffix}")
            st.warning("⚠️ Revise os dados antes de confirmar.")
            confirmacao = st.checkbox("Confirmo a operação acima", key=f"chk_confirmacao_{key_suffix}")
            submitted = st.button("💾 Salvar Registro", type="primary", key=f"btn_salvar_{key_suffix}")

        if submitted:
            campos_vazios = [k.replace("_", " ").title() for k, v in input_values.items() if v is None]
            if campos_vazios:
                msg_placeholder.error(f"❌ Verifique os seguintes campos (obrigatórios ou com valores inválidos): {', '.join(campos_vazios)}")
            elif not confirmacao:
                msg_placeholder.error("❌ Por favor, marque a caixa 'Confirmo a operação acima' para prosseguir.")
            else:
                is_valid = True
                if tabela_selecionada == "Pedigree":
                    id_animal_atual, id_pai_atual, id_mae_atual = input_keys_dict.get("id_animal"), input_values.get("id_pai"), input_values.get("id_mae")
                    if id_animal_atual is not None:
                        if id_pai_atual is not None and id_animal_atual == id_pai_atual:
                            msg_placeholder.error("❌ O animal não pode ser pai dele mesmo."); is_valid = False
                        elif id_mae_atual is not None and id_animal_atual == id_mae_atual:
                            msg_placeholder.error("❌ O animal não pode ser mãe dele mesmo."); is_valid = False
                    if id_pai_atual is not None and id_mae_atual is not None and id_pai_atual == id_mae_atual:
                        msg_placeholder.error("❌ O pai e a mãe não podem ser o mesmo animal."); is_valid = False
                
                if is_valid:
                    sucesso, erro_msg = save_record(tabela_selecionada, input_keys_dict, input_values, anulado, is_update=existe)
                    if sucesso:
                        msg_placeholder.success(f"Registro salvo com sucesso! Atualizando...")
                        time.sleep(1.5); st.rerun()
                    else:
                        msg_placeholder.error(f"❌ {erro_msg}")
    else:
        st.info("💡 Selecione ou informe a(s) chave(s) base na coluna à esquerda para abrir a área de manutenção.")