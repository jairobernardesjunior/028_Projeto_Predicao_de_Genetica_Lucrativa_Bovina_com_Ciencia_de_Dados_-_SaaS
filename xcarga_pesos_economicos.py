import sqlite3
import pandas as pd
import os

# Definição dos caminhos dos arquivos
# Ajuste o caminho do banco de dados se ele estiver em outra pasta (ex: r"C:\boigene\bd\boigene_db.db")
DB_PATH = 'c:/boigene/bd/boigene_db.db'
CSV_PATH = 'C:/projetos_gerais/Projetos_ciedados/028_Projeto_blupf90_Predição_de_Genética_Lucrativa_Bovina_com_Ciência_de_Dados_&_SaaS/dataset/dataset BLUPF90/00 ORIGINAIS/pesos_economicos.csv'

def realizar_carga_pesos():
    print(f"Iniciando carga de dados do arquivo '{CSV_PATH}' para '{DB_PATH}'...")

    # 1. Verifica se o arquivo CSV existe
    if not os.path.exists(CSV_PATH):
        print(f"❌ Erro: O arquivo {CSV_PATH} não foi encontrado no diretório atual.")
        return

    # 2. Lê o arquivo CSV
    try:
        # Lendo com separador ';' e encoding utf-8-sig (padrão que geramos antes)
        df_pesos = pd.read_csv(CSV_PATH, sep=';', encoding='utf-8-sig')
        print(f"✅ CSV lido com sucesso! {len(df_pesos)} registros encontrados.")
    except Exception as e:
        print(f"❌ Erro ao ler o arquivo CSV: {e}")
        return

    # 3. Prepara os dados (adicionando a coluna 'anulado' exigida pelo esquema do banco)
    if 'anulado' not in df_pesos.columns:
        df_pesos['anulado'] = 0

    # 4. Conecta ao banco e insere os dados
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Garante que a tabela exista (caso o cadastro_base.py ainda não tenha sido executado)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pesos_economicos (
                id_peso INTEGER PRIMARY KEY,
                descricao TEXT,
                nome_peso TEXT,
                valor_estimado REAL,
                anulado INTEGER DEFAULT 0
            )
        ''')
        
        # Converte o DataFrame para uma lista de tuplas para inserção segura
        # Colunas esperadas: id_peso, descricao, nome_peso, valor_estimado, anulado
        registros = df_pesos[['id_peso', 'descricao', 'nome_peso', 'valor_estimado', 'anulado']].values.tolist()
        
        # Comando SQL de inserção (usando INSERT OR REPLACE para evitar duplicação se rodar 2 vezes)
        sql_insert = '''
            INSERT OR REPLACE INTO pesos_economicos 
            (id_peso, descricao, nome_peso, valor_estimado, anulado) 
            VALUES (?, ?, ?, ?, ?)
        '''
        
        cursor.executemany(sql_insert, registros)
        conn.commit()
        
        print(f"✅ Carga concluída! {cursor.rowcount} linhas inseridas/atualizadas na tabela 'pesos_economicos'.")
        
    except sqlite3.Error as e:
        print(f"❌ Erro de banco de dados SQLite: {e}")
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
            print("🔌 Conexão com o banco de dados encerrada.")

if __name__ == "__main__":
    realizar_carga_pesos()