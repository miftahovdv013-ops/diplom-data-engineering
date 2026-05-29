import psycopg2
from datetime import datetime

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'dwh_db',
    'user': 'postgres',
    'password': 'postgres'
}

def create_dq_tables():
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    cursor.execute("DROP TABLE IF EXISTS meta.dq_log CASCADE")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meta.dq_log (
            log_id SERIAL PRIMARY KEY,
            check_name VARCHAR(100) NOT NULL,
            check_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) NOT NULL,
            error_count INTEGER DEFAULT 0,
            error_message TEXT,
            severity VARCHAR(20),
            table_name VARCHAR(50)
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
    print("аблица meta.dq_log создана")

def run_data_quality_checks():
    
    create_dq_tables()
    
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    

    # Проверка дубликатов
    print("\nПроверка дубликатов invoice_id")
    cursor.execute("""
        SELECT COUNT(*) FROM (
            SELECT invoice_id, COUNT(*) 
            FROM nds.fact_invoice 
            GROUP BY invoice_id 
            HAVING COUNT(*) > 1
        ) dup
    """)
    duplicates = cursor.fetchone()[0]
    
    if duplicates > 0:
        cursor.execute("""
            INSERT INTO meta.dq_log (check_name, status, error_count, severity, table_name)
            VALUES ('duplicate_invoices', 'FAILED', %s, 'HIGH', 'nds.fact_invoice')
        """, (duplicates,))
        print(f"{duplicates} дубликатов")
    else:
        cursor.execute("""
            INSERT INTO meta.dq_log (check_name, status, error_count, severity, table_name)
            VALUES ('duplicate_invoices', 'PASSED', 0, 'LOW', 'nds.fact_invoice')
        """)
        print("Дубликатов не найдено")
    
    # Проверка NULL значений
    print("\nПроверка NULL значений")
    cursor.execute("""
        SELECT COUNT(*) FROM nds.fact_invoice 
        WHERE invoice_id IS NULL OR total_amount IS NULL
    """)
    nulls = cursor.fetchone()[0]
    
    if nulls > 0:
        cursor.execute("""
            INSERT INTO meta.dq_log (check_name, status, error_count, severity, table_name)
            VALUES ('null_values', 'FAILED', %s, 'HIGH', 'nds.fact_invoice')
        """, (nulls,))
        print(f"{nulls} NULL значений")
    else:
        cursor.execute("""
            INSERT INTO meta.dq_log (check_name, status, error_count, severity, table_name)
            VALUES ('null_values', 'PASSED', 0, 'LOW', 'nds.fact_invoice')
        """)
        print("NULL значений не найдено")
    
    # 3. Проверка рейтинга
    print("\nПроверка диапазона рейтинга")
    cursor.execute("""
        SELECT COUNT(*) FROM nds.fact_invoice 
        WHERE rating < 0 OR rating > 10
    """)
    bad_ratings = cursor.fetchone()[0]
    
    if bad_ratings > 0:
        cursor.execute("""
            INSERT INTO meta.dq_log (check_name, status, error_count, severity, table_name)
            VALUES ('rating_range', 'FAILED', %s, 'MEDIUM', 'nds.fact_invoice')
        """, (bad_ratings,))
        print(f"{bad_ratings} записей с рейтингом вне диапазона")
    else:
        cursor.execute("""
            INSERT INTO meta.dq_log (check_name, status, error_count, severity, table_name)
            VALUES ('rating_range', 'PASSED', 0, 'LOW', 'nds.fact_invoice')
        """)
        print("Все рейтинги в диапазоне 0-10")
    
    # 4. Проверка количества
    print("\nПроверка количества товаров")
    cursor.execute("""
        SELECT COUNT(*) FROM nds.fact_invoice WHERE quantity <= 0
    """)
    bad_qty = cursor.fetchone()[0]
    
    if bad_qty > 0:
        cursor.execute("""
            INSERT INTO meta.dq_log (check_name, status, error_count, severity, table_name)
            VALUES ('quantity_positive', 'FAILED', %s, 'HIGH', 'nds.fact_invoice')
        """, (bad_qty,))
        print(f"{bad_qty} записей с quantity <= 0!")
    else:
        cursor.execute("""
            INSERT INTO meta.dq_log (check_name, status, error_count, severity, table_name)
            VALUES ('quantity_positive', 'PASSED', 0, 'LOW', 'nds.fact_invoice')
        """)
        print("Все quantity > 0")
    
    conn.commit()
    cursor.close()
    conn.close()

if __name__ == "__main__":
    run_data_quality_checks()