import pandas as pd
import psycopg2

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'dwh_db',
    'user': 'postgres',
    'password': 'postgres'
}

conn = psycopg2.connect(**DB_CONFIG)

df = pd.read_sql("""
    SELECT 
        invoice_id, invoice_date, invoice_time, city, product_line_name,
        customer_type, gender, payment_method, quantity, unit_price,
        total_amount, gross_income, rating
    FROM mart.detailed_sales
    LIMIT 10000
""", conn)

df.to_csv('/root/airflow_project/detailed_sales.csv', index=False)

daily = pd.read_sql("""
    SELECT d.full_date, SUM(f.total_amount) as revenue
    FROM dds.fact_sales f
    JOIN dds.dim_date d ON f.date_key = d.date_key
    GROUP BY d.full_date
    ORDER BY d.full_date
""", conn)

daily.to_csv('/root/airflow_project/daily_sales.csv', index=False)

products = pd.read_sql("""
    SELECT product_line_name, unit_price, price_category
    FROM dds.dim_product
    ORDER BY unit_price DESC
""", conn)

products.to_csv('/root/airflow_project/products.csv', index=False)

branches = pd.read_sql("""
    SELECT branch_code, city
    FROM dds.dim_branch
""", conn)

branches.to_csv('/root/airflow_project/branches.csv', index=False)

try:
    forecast = pd.read_sql("""
        SELECT date, predicted_revenue, lower_bound, upper_bound
        FROM ml.sales_forecast
    """, conn)
    forecast.to_csv('/root/airflow_project/forecast.csv', index=False)
    print("Прогноз экспортирован")
except Exception as e:
    print(f"Прогноз не найден: {e}")
finally:
    conn.close()