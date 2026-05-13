import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import psycopg2
from psycopg2 import sql
from logger import get_logger

logger = get_logger(__name__)

# --- Constants ---
# It's better to get these from environment variables
DB_HOST = config.DB_HOST
DB_PORT = config.DB_PORT
DB_NAME = config.DB_NAME
DB_USER = config.DB_USER
DB_PASSWORD = config.DB_PASSWORD
TABLE_NAME = config.DB_TABLE_NAME

def create_database_and_table():
    """
    Connects to the PostgreSQL database and creates the qa_logs2 table
    if it hasn't been created yet.
    """
    conn = None
    try:
        # Connect to PostgreSQL database
        conn = psycopg2.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            dbname=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD
        )
        cursor = conn.cursor()

        # SQL statement to create a table in PostgreSQL
        # Using SERIAL for auto-incrementing primary key
        # Using TIMESTAMP WITH TIME ZONE for better timezone handling
        # Using JSONB for efficient JSON storage
        create_table_query = sql.SQL("""
        CREATE TABLE IF NOT EXISTS {table} (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            request_id VARCHAR(36),
            session_id VARCHAR(36),
            user_id VARCHAR(36),
            question TEXT NOT NULL,
            rephrased_question TEXT,
            answer TEXT,
            retrieved_contexts JSONB, -- Storing as JSONB
            faithfulness_score REAL,
            response_relevancy_score REAL,
            context_precision_score REAL,
            latency_ms REAL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            feedback_type TEXT,
            feedback_text TEXT,
            feedback_token_hash VARCHAR(64)
        );
        """).format(table=sql.Identifier(TABLE_NAME))

        # Execute the SQL statement
        cursor.execute(create_table_query)

        # Create scholarships table
        create_scholarships_table_query = sql.SQL("""
        CREATE TABLE IF NOT EXISTS tcuscholarships (
            scholarship_code VARCHAR(50) PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            link TEXT,
            category VARCHAR(255),
            education_system JSONB,
            tags JSONB,
            identity JSONB,
            registered_residence JSONB,
            nationality JSONB,
            amount_summary TEXT,
            description TEXT,
            application_date_text TEXT,
            contact TEXT,
            markdown_content TEXT,
            content_hash VARCHAR(255),
            last_checked_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            pending_data JSONB,
            needs_review BOOLEAN DEFAULT FALSE
        );
        """)
        cursor.execute(create_scholarships_table_query)

        # --- Migration: 為已存在的資料表安全新增欄位 ---
        migration_queries = [
            sql.SQL("ALTER TABLE {table} ADD COLUMN IF NOT EXISTS request_id VARCHAR(36);").format(table=sql.Identifier(TABLE_NAME)),
            sql.SQL("ALTER TABLE {table} ADD COLUMN IF NOT EXISTS session_id VARCHAR(36);").format(table=sql.Identifier(TABLE_NAME)),
            sql.SQL("ALTER TABLE {table} ADD COLUMN IF NOT EXISTS user_id VARCHAR(36);").format(table=sql.Identifier(TABLE_NAME)),
            sql.SQL("ALTER TABLE {table} ADD COLUMN IF NOT EXISTS feedback_token_hash VARCHAR(64);").format(table=sql.Identifier(TABLE_NAME)),
            sql.SQL("ALTER TABLE tcuscholarships ADD COLUMN IF NOT EXISTS registered_residence JSONB;"),
            sql.SQL("ALTER TABLE tcuscholarships ADD COLUMN IF NOT EXISTS nationality JSONB;"),
        ]
        for mq in migration_queries:
            cursor.execute(mq)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_refresh_tokens (
            jti VARCHAR(64) PRIMARY KEY,
            token_hash VARCHAR(64) NOT NULL,
            subject VARCHAR(255) NOT NULL,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            revoked_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Commit the changes
        conn.commit()
        logger.info(f"Database '{DB_NAME}', table '{TABLE_NAME}', and 'tcuscholarships' table are set up successfully in PostgreSQL.")

    except psycopg2.Error as e:
        # 🚨 ERROR：資料庫建立錯誤
        logger.error(f"[DB] Database error: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    create_database_and_table()
