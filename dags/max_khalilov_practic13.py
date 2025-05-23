from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from airflow.sensors.external_task import ExternalTaskSensor 
from airflow.sensors.time_delta import TimeDeltaSensor 
from airflow.hooks.base import BaseHook

from operators.operator_combine_date_max_khalilov import CustomCombineDataOperator
from operators.upload_data_operator_max_khalilov import CustomUploadDataOperator
from sensors.les_15_sensor_max_khalilov import SqlSensor

DEFAULT_ARGS = {
    'owner': 'admin',
    'retries': 2,
    'retry_delay': 600,
    'start_date': datetime(2025, 4, 14)
}

API_URL = 'https://b2b.itresume.ru/api/statistics'

def load_from_api(**context):
    import requests 
    import psycopg2 as pg
    import ast 

    execution_date = context['execution_date']
    # Получаем начало недели (понедельник)
    start_of_week = execution_date - timedelta(days=execution_date.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    # Получаем конец недели (воскресенье)
    end_of_week = start_of_week + timedelta(days=6)
    end_of_week = end_of_week.replace(hour=23, minute=59, second=59)

    start_str = start_of_week.strftime('%Y-%m-%d')
    end_str = end_of_week.strftime('%Y-%m-%d')

    payload = {
        'client': 'Skillfactory',
        'client_key': 'M2MGWS',
        'start': start_str,
        'end': end_str
    }

    response = requests.get(API_URL, params=payload)
    data = response.json()

    connection = BaseHook.get_connection('conn_pg')

    with pg.connect(
        dbname='etl',
        sslmode='disable',
        user=connection.login,
        password=connection.password,
        host=connection.host,
        port=connection.port,
        connect_timeout=600,
        keepalives_idle=600,
        tcp_user_timeout=600
    ) as conn:
        cursor = conn.cursor()

        # Проверка количества записей до очистки
        cursor.execute("SELECT COUNT(*) FROM maks_khalilov")
        count_before = cursor.fetchone()[0]

        cursor.execute("TRUNCATE TABLE maks_khalilov")
    
        for el in data:
            row = []
            passback_params = ast.literal_eval(el.get('passback_params') if el.get('passback_params') else '{}')
            row.append(el.get('lti_user_id'))
            row.append(True if el.get('is_correct') == 1 else False)
            row.append(el.get('attempt_type'))
            row.append(el.get('created_at'))
            row.append(passback_params.get('oauth_consumer_key'))
            row.append(passback_params.get('lis_result_sourcedid'))
            row.append(passback_params.get('lis_outcome_service_url'))

            cursor.execute("INSERT INTO maks_khalilov VALUES (%s, %s, %s, %s, %s, %s, %s)", row)

        conn.commit()


with DAG(
    dag_id='max_khalilov_practic13',
    tags=['max_khalilov', '7'],
    default_args=DEFAULT_ARGS,
    schedule='@daily',
    max_active_runs=1,
    max_active_tasks=1
) as dag:
    
    start_dag = EmptyOperator(task_id='start_dag')
    end_dagg = EmptyOperator(task_id='end_dag')

    load_from_api = PythonOperator(
        task_id='load_from_api',
        python_callable=load_from_api
    )

    combine_data = CustomCombineDataOperator(
        task_id='combine_data',
    )

    upload_data = CustomUploadDataOperator(
        task_id='upload_data',
    )

    start_dag >> load_from_api >> combine_data >> upload_data >> end_dagg



