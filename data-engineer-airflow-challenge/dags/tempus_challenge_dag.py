"""Simple DAG that uses a few python operators."""
import os
from datetime import datetime, timedelta

import challenge.news as news
from airflow import DAG
from airflow.operators.python_operator import PythonOperator

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2018, 4, 1),
    "email": ["airflow@airflow.com"],
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=5),
}

s3_bucket = os.getenv("TEMPUS_DAG_S3_BUCKET", "dummy-bucket")
apikey = os.getenv("TEMPUS_DAG_NEWSAPI_KEY", "dummykey")

# DAG Object
dag = DAG(
    "tempus_challenge_dag",
    default_args=default_args,
    schedule_interval="@daily",  # DAG will run daily
    catchup=False,
)

headlines_task = PythonOperator(
    task_id="headlines_task",
    provide_context=True,
    python_callable=news.generate_headlines,
    op_kwargs={"tmpdir": "/tmp", "bucket": s3_bucket, "apikey": apikey},
    dag=dag,
)

search_task = PythonOperator(
    task_id="search_task",
    provide_context=True,
    python_callable=news.search_news,
    op_kwargs={
        "tmpdir": "/tmp",
        "bucket": s3_bucket,
        "apikey": apikey,
        "terms": ["Tempus Labs", "Eric Lefkosky", "cancer", "immunotherapy"],
    },
    dag=dag,
)
