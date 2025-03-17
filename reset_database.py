import os
import sys
import psycopg2
import subprocess
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 添加项目根目录到 Python 路径
sys.path.append(".")
from dlmonitor.settings import DATABASE_URL, DATABASE_ADDR, DATABASE_NAME, DATABASE_USER, DATABASE_PASSWD
from dlmonitor.db_models import Base

def reset_database():
    print("Connecting to PostgreSQL database...")
    
    # 连接到 postgres 数据库（不是项目数据库）
    conn_string = f"postgresql://{DATABASE_USER}:{DATABASE_PASSWD}@{DATABASE_ADDR}/postgres"
    conn = psycopg2.connect(conn_string)
    conn.autocommit = True
    cursor = conn.cursor()
    
    # 强制断开所有到目标数据库的连接
    print(f"Terminating all connections to database {DATABASE_NAME}...")
    cursor.execute(f"""
    SELECT pg_terminate_backend(pg_stat_activity.pid)
    FROM pg_stat_activity
    WHERE pg_stat_activity.datname = '{DATABASE_NAME}'
    AND pid <> pg_backend_pid();
    """)
    
    # 删除旧数据库（如果存在）
    print(f"Dropping database {DATABASE_NAME} if it exists...")
    cursor.execute(f"DROP DATABASE IF EXISTS {DATABASE_NAME}")
    
    # 创建新数据库
    print(f"Creating database {DATABASE_NAME}...")
    cursor.execute(f"CREATE DATABASE {DATABASE_NAME}")
    
    # 关闭与 postgres 数据库的连接
    cursor.close()
    conn.close()
    
    # 使用超级用户创建 pgvector 扩展
    print("Creating pgvector extension as superuser...")
    try:
        subprocess.run(["sudo", "-u", "postgres", "psql", "-d", DATABASE_NAME, "-c", "CREATE EXTENSION IF NOT EXISTS vector;"], check=True)
        print("Successfully created pgvector extension.")
    except subprocess.CalledProcessError as e:
        print(f"Error creating pgvector extension: {e}")
        print("You may need to manually create the extension with: sudo -u postgres psql -d dlmonitor -c 'CREATE EXTENSION IF NOT EXISTS vector;'")
    
    # 连接到新创建的数据库
    print(f"Connecting to {DATABASE_NAME}...")
    engine = create_engine(DATABASE_URL)
    
    # 创建所有表格
    print("Creating tables...")
    Base.metadata.create_all(engine)
    
    print("Database reset complete!")

if __name__ == "__main__":
    # 确认操作
    print("WARNING: This will delete the existing database and create a new one.")
    response = input("Are you sure you want to continue? (y/n): ")
    
    if response.lower() == 'y':
        reset_database()
    else:
        print("Operation cancelled.") 