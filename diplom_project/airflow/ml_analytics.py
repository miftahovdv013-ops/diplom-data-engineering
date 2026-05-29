import pandas as pd
import numpy as np
import psycopg2
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from datetime import datetime, timedelta

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'dwh_db',
    'user': 'postgres',
    'password': 'postgres'
}

print("="*50)
print("ML АНАЛИТИКА — МОДЕЛЬ «АДАПТИВНЫЙ ТРЕНД»")
print("="*50)

conn = psycopg2.connect(**DB_CONFIG)

df = pd.read_sql("""
    SELECT d.full_date, SUM(f.total_amount) as revenue
    FROM dds.fact_sales f
    JOIN dds.dim_date d ON f.date_key = d.date_key
    GROUP BY d.full_date
    ORDER BY d.full_date
""", conn)

conn.close()

print(f"   Загружено {len(df)} дней")
print(f"   Период: с {df['full_date'].min()} по {df['full_date'].max()}")
print(f"   Средняя выручка: ${df['revenue'].mean():,.0f}")

volatility = df['revenue'].std() / df['revenue'].mean()
print(f"   Волатильность: {volatility:.2f}")

if volatility > 0.25:
    window = 14
elif volatility > 0.15:
    window = 7
else:
    window = 3

print(f"   Используем окно сглаживания: {window} дней")

df_smooth = df.copy()
df_smooth['revenue_smoothed'] = df_smooth['revenue'].rolling(window, center=True).mean()
df_smooth = df_smooth.dropna().reset_index(drop=True)

df_recent = df_smooth.tail(30).copy()
print(f"   Обучаемся на последних {len(df_recent)} днях")

df_recent.loc[:, 'trend'] = range(len(df_recent))
df_recent.loc[:, 'trend2'] = df_recent['trend'] ** 2
df_recent.loc[:, 'day_of_week'] = pd.to_datetime(df_recent['full_date']).dt.dayofweek
df_recent.loc[:, 'is_weekend'] = (df_recent['day_of_week'] >= 5).astype(int)
df_recent.loc[:, 'month'] = pd.to_datetime(df_recent['full_date']).dt.month
df_recent.loc[:, 'week_of_month'] = (pd.to_datetime(df_recent['full_date']).dt.day - 1) // 7 + 1

weights = np.exp(np.linspace(-0.5, 0, len(df_recent)))
weights = weights / weights.sum()

X = df_recent[['trend', 'trend2', 'day_of_week', 'is_weekend', 'month', 'week_of_month']]
y = df_recent['revenue_smoothed']

split_idx = int(len(df_recent) * 0.8)
X_train = X[:split_idx]
X_test = X[split_idx:]
y_train = y[:split_idx]
y_test = y[split_idx:]

model = Ridge(alpha=1.0)
model.fit(X_train, y_train, sample_weight=weights[:split_idx])

y_pred_test = model.predict(X_test)
test_r2 = r2_score(y_test, y_pred_test)
test_mae = mean_absolute_error(y_test, y_pred_test)
test_mape = np.mean(np.abs((y_test - y_pred_test) / y_test)) * 100

print(f"\n   R² тест = {test_r2:.3f}")
print(f"   MAE тест = ${test_mae:,.0f}")
print(f"   MAPE тест = {test_mape:.1f}%")

last_date = df_recent['full_date'].iloc[-1]
last_trend = df_recent['trend'].iloc[-1]

future_data = []
for i in range(1, 8):
    date = last_date + timedelta(days=i)
    features = pd.DataFrame([[
        last_trend + i,
        (last_trend + i) ** 2,
        date.weekday(),
        1 if date.weekday() >= 5 else 0,
        date.month,
        (date.day - 1) // 7 + 1
    ]], columns=['trend', 'trend2', 'day_of_week', 'is_weekend', 'month', 'week_of_month'])
    pred = model.predict(features)[0]
    future_data.append({
        'date': date.strftime('%Y-%m-%d'),
        'weekday': date.strftime('%A'),
        'predicted_revenue': round(max(pred, 0), 2),
        'lower_bound': round(max(pred * 0.85, 0), 2),
        'upper_bound': round(pred * 1.15, 2)
    })

forecast_df = pd.DataFrame(future_data)
forecast_df.to_csv('/root/airflow_project/forecast.csv', index=False)