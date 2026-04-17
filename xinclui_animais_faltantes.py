import sqlite3
import logging

# Configuração básica de log para monitoramento
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def sincronizar_animais_ambiente(db_path):
    """
    Identifica id_animal na tabela 'ambiente' que não existem em 'cadastro_animais'
    e os insere com a descrição formatada.
    """
    conn = None
    try:
        # 1. Conectar ao banco de dados SQLite
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        logging.info(f"Conectado ao banco: {db_path}")

        # 2. SQL para inserção em lote
        # Usamos o operador de concatenação || do SQLite para formar a descrição
        # O NOT EXISTS ou EXCEPT garante que não tentaremos inserir IDs duplicados
        query = """
        INSERT INTO cadastro_animais (id_animal, descricao_animal)
        SELECT DISTINCT a.id_animal, 'animal ' || a.id_animal
        FROM ambiente a
        WHERE NOT EXISTS (
            SELECT 1 
            FROM cadastro_animais c 
            WHERE c.id_animal = a.id_animal
        );
        """
        
        # 3. Executar a operação
        cursor.execute(query)
        linhas_inseridas = cursor.rowcount
        
        # 4. Confirmar as alterações
        conn.commit()
        
        if linhas_inseridas > 0:
            logging.info(f"Sucesso! {linhas_inseridas} novos registros inseridos em 'cadastro_animais'.")
        else:
            logging.info("Nenhum animal novo encontrado para sincronização.")

    except sqlite3.Error as e:
        logging.error(f"Erro de banco de dados: {e}")
        if conn:
            conn.rollback() # Reverte em caso de erro
    except Exception as e:
        logging.error(f"Erro inesperado: {e}")
    finally:
        # 5. Fechar conexão com segurança
        if conn:
            conn.close()
            logging.info("Conexão encerrada.")

if __name__ == "__main__":
    # Caminho do arquivo enviado
    DATABASE_NAME = 'boigene_db.db'
    sincronizar_animais_ambiente(DATABASE_NAME)