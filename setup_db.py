import sqlite3
import os

def setup_database():
    # Remove existing database if it exists
    if os.path.exists("context.db"):
        os.remove("context.db")
    
    with sqlite3.connect("context.db") as conn:
        cursor = conn.cursor()

        # Create context table for session storage
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS context (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            role TEXT,
            content TEXT,
            is_fact BOOLEAN DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        """)

        # Create facts table for long-term storage
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            id TEXT PRIMARY KEY,
            role TEXT,
            content TEXT,
            source_session TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_session) REFERENCES sessions(id)
        );
        """)

        # Create sessions table to track conversation sessions
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            end_time DATETIME,
            facts_count INTEGER DEFAULT 0
        );
        """)

        conn.commit()
        print("[green]Database initialized with MCP architecture.[/green]")

if __name__ == "__main__":
    setup_database()
