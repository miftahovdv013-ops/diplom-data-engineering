from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

default_args = {
    'owner': 'data_engineer',
    'start_date': datetime(2024, 1, 1),
    'retries': 1,
}

PYTHON = '/root/airflow_project/venv/bin/python'

with DAG(
    dag_id='etl_pipeline',
    default_args=default_args,
    description='ETL пайплайн',
    schedule='@daily',
    catchup=False,
) as dag:
    
    start = EmptyOperator(task_id='start')
    
    run_etl = BashOperator(
        task_id='run_etl',
        bash_command=f'{PYTHON} /root/airflow_project/etl_airflow.py',
    )
    
    run_quality = BashOperator(
        task_id='run_data_quality',
        bash_command=f'{PYTHON} /root/airflow_project/data_quality.py',
    )
    
    run_ml = BashOperator(
        task_id='run_ml_analytics',
        bash_command=f'{PYTHON} /root/airflow_project/ml_analytics.py',
    )
    
    run_export = BashOperator(
        task_id='run_export',
        bash_command=f'{PYTHON} /root/airflow_project/export_metadata.py',
    )
    
    end = EmptyOperator(task_id='end')
    
    start >> run_etl >> run_quality >> run_ml >> run_export >> end
