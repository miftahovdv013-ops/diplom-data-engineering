import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from sqlalchemy import create_engine

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'dwh_db',
    'user': 'postgres',
    'password': 'postgres'
}

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

cursor.execute("ROLLBACK")
conn.commit()

cursor.execute("TRUNCATE TABLE dds.fact_sales CASCADE")
cursor.execute("TRUNCATE TABLE nds.fact_invoice CASCADE")
cursor.execute("TRUNCATE TABLE nds.dim_branch CASCADE")
cursor.execute("TRUNCATE TABLE nds.dim_payment CASCADE")
cursor.execute("TRUNCATE TABLE nds.dim_product_line CASCADE")
cursor.execute("TRUNCATE TABLE nds.dim_customer_type CASCADE")
cursor.execute("TRUNCATE TABLE nds.dim_gender CASCADE")
conn.commit()

df = pd.read_csv('/root/airflow_project/sales.csv', parse_dates=['Date'])
df['Time'] = pd.to_datetime(df['Time'], format='%H:%M').dt.time

branches = df[['Branch', 'City']].drop_duplicates()
for _, row in branches.iterrows():
    cursor.execute("INSERT INTO nds.dim_branch (branch_code, city) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                   (row['Branch'], row['City']))

for payment in df['Payment'].unique():
    cursor.execute("INSERT INTO nds.dim_payment (payment_method) VALUES (%s) ON CONFLICT DO NOTHING", (payment,))

products = df[['Product line', 'Unit price']].drop_duplicates()
for _, row in products.iterrows():
    cursor.execute("INSERT INTO nds.dim_product_line (product_line_name, unit_price) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                   (row['Product line'], row['Unit price']))

for ct in df['Customer type'].unique():
    cursor.execute("INSERT INTO nds.dim_customer_type (type_name) VALUES (%s) ON CONFLICT DO NOTHING", (ct,))

for gender in df['Gender'].unique():
    cursor.execute("INSERT INTO nds.dim_gender (gender_name) VALUES (%s) ON CONFLICT DO NOTHING", (gender,))

conn.commit()

cursor.execute("SELECT branch_code, branch_id FROM nds.dim_branch")
branch_map = dict(cursor.fetchall())

cursor.execute("SELECT payment_method, payment_id FROM nds.dim_payment")
payment_map = dict(cursor.fetchall())

cursor.execute("SELECT product_line_name, product_line_id FROM nds.dim_product_line")
product_map = dict(cursor.fetchall())

cursor.execute("SELECT type_name, customer_type_id FROM nds.dim_customer_type")
customer_type_map = dict(cursor.fetchall())

cursor.execute("SELECT gender_name, gender_id FROM nds.dim_gender")
gender_map = dict(cursor.fetchall())


facts = []
for _, row in df.iterrows():
    facts.append((
        row['Invoice ID'], row['Date'], row['Time'],
        branch_map[row['Branch']],
        customer_type_map[row['Customer type']],
        gender_map[row['Gender']],
        payment_map[row['Payment']],
        product_map[row['Product line']],
        row['Quantity'], row['Unit price'],
        row['Total'], row['Tax 5%'], row['cogs'], row['gross income'], row['Rating']
    ))

execute_batch(cursor, """
    INSERT INTO nds.fact_invoice VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (invoice_id) DO NOTHING
""", facts)
conn.commit()

cursor.execute("TRUNCATE TABLE dds.dim_branch CASCADE")
cursor.execute("TRUNCATE TABLE dds.dim_product CASCADE")
cursor.execute("TRUNCATE TABLE dds.dim_customer CASCADE")
cursor.execute("TRUNCATE TABLE dds.dim_payment CASCADE")
cursor.execute("TRUNCATE TABLE dds.fact_sales CASCADE")

cursor.execute("INSERT INTO dds.dim_branch (branch_id, branch_code, city) SELECT branch_id, branch_code, city FROM nds.dim_branch")

cursor.execute("""
    INSERT INTO dds.dim_product (product_line_id, product_line_name, unit_price, price_category)
    SELECT product_line_id, product_line_name, unit_price,
        CASE WHEN unit_price < 30 THEN 'Budget' WHEN unit_price < 70 THEN 'Medium' ELSE 'Premium' END
    FROM nds.dim_product_line
""")

cursor.execute("""
    INSERT INTO dds.dim_customer (customer_type_id, customer_type_name, gender_id, gender_name, customer_segment)
    SELECT ct.customer_type_id, ct.type_name, g.gender_id, g.gender_name, ct.type_name || '_' || g.gender_name
    FROM nds.dim_customer_type ct CROSS JOIN nds.dim_gender g
""")

cursor.execute("""
    INSERT INTO dds.dim_payment (payment_id, payment_method, payment_type)
    SELECT payment_id, payment_method,
        CASE WHEN payment_method IN ('Ewallet','Credit card') THEN 'Digital' ELSE 'Cash' END
    FROM nds.dim_payment
""")

conn.commit()

cursor.execute("""
    INSERT INTO dds.fact_sales (invoice_id, date_key, branch_key, product_key, customer_key, payment_key,
                                quantity, unit_price, total_amount, tax_amount, gross_income, rating)
    SELECT fi.invoice_id,
        (EXTRACT(YEAR FROM fi.invoice_date)*10000 + EXTRACT(MONTH FROM fi.invoice_date)*100 + EXTRACT(DAY FROM fi.invoice_date))::int,
        db.branch_key, dp.product_key, dc.customer_key, dpm.payment_key,
        fi.quantity, fi.unit_price, fi.total_amount, fi.tax_amount, fi.gross_income, fi.rating
    FROM nds.fact_invoice fi
    JOIN dds.dim_branch db ON fi.branch_id = db.branch_id
    JOIN dds.dim_product dp ON fi.product_line_id = dp.product_line_id
    JOIN dds.dim_customer dc ON fi.customer_type_id = dc.customer_type_id AND fi.gender_id = dc.gender_id
    JOIN dds.dim_payment dpm ON fi.payment_id = dpm.payment_id
""")
conn.commit()

cursor.execute("SELECT COUNT(*) FROM dds.fact_sales")
fact_count = cursor.fetchone()[0]


cursor.execute("""
    DROP TABLE IF EXISTS mart.detailed_sales;

    CREATE TABLE mart.detailed_sales AS
    SELECT
        fi.invoice_id, fi.invoice_date, fi.invoice_time,
        b.city, pl.product_line_name, ct.type_name as customer_type,
        g.gender_name as gender, p.payment_method,
        fi.quantity, fi.unit_price, fi.total_amount, fi.gross_income, fi.rating
    FROM nds.fact_invoice fi
    JOIN nds.dim_branch b ON fi.branch_id = b.branch_id
    JOIN nds.dim_product_line pl ON fi.product_line_id = pl.product_line_id
    JOIN nds.dim_customer_type ct ON fi.customer_type_id = ct.customer_type_id
    JOIN nds.dim_gender g ON fi.gender_id = g.gender_id
    JOIN nds.dim_payment p ON fi.payment_id = p.payment_id
""")
conn.commit()
cursor.close()
conn.close()
