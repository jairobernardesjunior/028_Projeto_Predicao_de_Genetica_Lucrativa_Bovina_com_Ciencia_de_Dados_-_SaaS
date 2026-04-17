import sqlite3
import pandas as pd
import logging

# Configuração simples de log para acompanhamento
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def realizar_carga_sem_restricao(db_origem, db_destino):
    try:
        # Conectando aos bancos de dados
        conn_origem = sqlite3.connect(db_origem)
        conn_destino = sqlite3.connect(db_destino)
        
        # Desabilitar checagem de chaves estrangeiras (Integridade Referencial) no destino
        conn_destino.execute("PRAGMA foreign_keys = OFF;")
        
        # Lista de todas as tabelas (a ordem não importa mais com as FKs desligadas)
        tabelas_para_carga = [
            'cadastro_animais',
            'cadastro_categoria',
            'cadastro_estacao',
            'cadastro_fazenda',
            'cadastro_localidade',
            'cadastro_lote_manejo',
            'cadastro_pastagem',
            'cadastro_piquete',
            'cadastro_raca',
            'cadastro_regime_alim',
            'cadastro_sexo',
            'genotipos',
            'fenotipos',
            'pedigree',
            'relacao_ids',
            'ambiente'
        ]
        
        logging.info("Iniciando a carga de dados (Integridade Referencial DESLIGADA)...")

        for tabela in tabelas_para_carga:
            logging.info(f"Lendo e inserindo dados da tabela: {tabela}")
            
            # Extração dos dados da origem
            query = f"SELECT * FROM {tabela}"
            df_dados = pd.read_sql_query(query, conn_origem)
            
            if df_dados.empty:
                logging.info(f"  -> Tabela {tabela} está vazia na origem. Ignorando.")
                continue
            
            # Carga direta no destino sem transformação
            df_dados.to_sql(tabela, conn_destino, if_exists='append', index=False)
            logging.info(f"  -> {len(df_dados)} registros inseridos em '{tabela}'.")
            
        # Efetivar a transação
        conn_destino.commit()
        logging.info("Carga de todas as tabelas concluída com sucesso!")

    except Exception as e:
        logging.error(f"Erro durante a execução da carga: {e}")
    finally:
        # Garantir o fechamento das conexões
        if 'conn_origem' in locals(): conn_origem.close()
        if 'conn_destino' in locals(): conn_destino.close()

if __name__ == "__main__":
    banco_origem = 'novo_boigene_db.db'
    banco_destino = 'boigene_db.db'
    
    realizar_carga_sem_restricao(banco_origem, banco_destino)