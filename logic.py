# logic.py

import sqlite3
import os
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv
from rich.console import Console
from groq import Groq
import subprocess
import re

# Load environment variables from .env
load_dotenv()

DB_PATH = "context.db"
JSON_PATH = "context.json"
console = Console()

# Groq client for llama
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def init_db():
    """Initialize the database and start a new session."""
    if not os.path.exists(DB_PATH):
        from setup_db import setup_database
        setup_database()
    
    # Start new session
    session_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (id, start_time) 
        VALUES (?, CURRENT_TIMESTAMP)
    """, (session_id,))
    conn.commit()
    conn.close()
    
    # Load facts from GitHub
    pull_json_from_github()
    
    
    
    return session_id

def add_message(role, content, is_fact=False):
    """Add a message to the current session context."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Store both user and assistant messages
        message_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO context (id, role, content, is_fact) 
            VALUES (?, ?, ?, ?)
        """, (message_id, role, content, is_fact))
        
        # Save to context.json immediately (local only)
        try:
            # Read existing messages
            if os.path.exists(JSON_PATH):
                with open(JSON_PATH, "r", encoding="utf-8") as f:
                    messages = json.load(f)
            else:
                messages = []
            
            # Add new message
            messages.append({
                "id": message_id,
                "role": role,
                "content": content
            })
            
            # Save back to file (local only)
            with open(JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(messages, f, indent=2)
                
        except Exception as e:
            pass  # Silently handle errors
        
        conn.commit()
        conn.close()
    except Exception as e:
        pass  # Silently handle errors

def get_messages():
    """Get all messages from the current session."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get messages
    cursor.execute("""
        SELECT id, role, content, is_fact 
        FROM context 
        ORDER BY timestamp
    """)
    rows = cursor.fetchall()
    conn.close()
    
    messages = [{"id": _id, "role": role, "content": content, "is_fact": is_fact} 
            for _id, role, content, is_fact in rows]
    
    
    return messages

def get_facts():
    """Get only factual messages from the current session."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, role, content 
        FROM context 
        WHERE is_fact = 1 
        ORDER BY timestamp
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{"id": _id, "role": role, "content": content} 
            for _id, role, content in rows]

def save_session_to_github():
    """Save all messages from the current session to GitHub."""
    try:
        # Get all messages from the database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, role, content 
            FROM context 
            ORDER BY timestamp DESC
        """)
        messages = [{"id": _id, "role": role, "content": content} 
                for _id, role, content in cursor.fetchall()]
        conn.close()
        
        if not messages:
            console.print("[yellow]No messages to save.[/yellow]")
            return
        
        
        # Save messages to JSON
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(messages, f, indent=2)
        
        # Push to GitHub
        try:
            # Add the file
            subprocess.run(["git", "add", JSON_PATH], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Commit with timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commit_msg = f"Update conversation - {timestamp}"
            subprocess.run(["git", "commit", "-m", commit_msg], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Push changes
            subprocess.run(["git", "push"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
           
            
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to push to GitHub: {e}[/red]")
            # If push fails, try to pull first and then push again
            try:
                subprocess.run(["git", "pull", "--rebase"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["git", "push"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                console.print("[green]Successfully saved conversation to GitHub after resolving conflicts[/green]")
            except subprocess.CalledProcessError as e2:
                console.print(f"[red]Failed to resolve GitHub conflicts: {e2}[/red]")
    except Exception as e:
        console.print(f"[red]Error saving to GitHub: {e}[/red]")

def pull_json_from_github():
    """Pull facts from GitHub at session start."""
    try:
        # Pull latest changes
        subprocess.run(["git", "pull"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if os.path.exists(JSON_PATH):
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                facts = json.load(f)
            
            if facts:
               
                
                # Clear existing facts to avoid duplicates
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM facts")
                conn.commit()
                
                # Add facts to database
                for fact in facts:
                    add_message(fact["role"], fact["content"], is_fact=True)
                
                conn.close()
            
        else:
            console.print("[yellow]context.json not found in repository[/yellow]")
            
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to pull from GitHub: {e}[/red]")
    except json.JSONDecodeError as e:
        console.print(f"[red]Error parsing context: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error loading facts: {e}[/red]")

def clear_session():
    """End current session and start a new one."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # End current session
        cursor.execute("""
            UPDATE sessions 
            SET end_time = CURRENT_TIMESTAMP 
            WHERE end_time IS NULL
        """)
        
        # Clear context table
        cursor.execute("DELETE FROM context")
        conn.commit()
        conn.close()
        
        # Clear context.json
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
        
        # Start new session
        init_db()
        return True
    except Exception as e:
        return False

def is_fact_response(response: str) -> bool:
    """Determine if a response contains factual information or meaningful context."""
    # Keywords that indicate factual information
    fact_keywords = [
        # Technical facts
        " is ", " are ", " was ", " were ", " means ", " stands for ", " used to ",
        " include ", " such as ", " examples ", " definition ", " important ",
        " consists of ", " helps ", " allows ", " can be ", " typically ",
        " commonly ", " usually ", " consists ", " refers to ", " characteristics ",
        " types ", " consist of ", " based on ", " requires ", " needs ",
        " must ", " should ", " will ", " has ", " have ", " had ",
        # Technical relationships
        " connects ", " integrates ", " interacts ", " communicates ",
        " depends on ", " relies on ", " uses ", " implements ",
        # Technical properties
        " property ", " attribute ", " feature ", " capability ",
        " functionality ", " behavior ", " structure ", " architecture ",
        # Technical actions
        " performs ", " executes ", " processes ", " handles ",
        " manages ", " controls ", " operates ", " functions ",
        # Technical states
        " state ", " status ", " condition ", " mode ",
        " configuration ", " setting ", " parameter ",
        # General facts
        " because ", " since ", " as ", " due to ", " therefore ", " thus ",
        " in fact ", " actually ", " indeed ", " specifically ", " particularly ",
        " especially ", " notably ", " importantly ", " significantly ",
        " primarily ", " mainly ", " mostly ", " largely ", " generally ",
        " typically ", " usually ", " commonly ", " frequently ", " often ",
        " always ", " never ", " sometimes ", " occasionally ", " rarely "
    ]
    
    response_lower = response.lower()
    
    # Check for fact keywords
    has_fact_keywords = any(keyword in response_lower for keyword in fact_keywords)
    
    # Check for technical terms
    technical_terms = ["api", "database", "server", "client", "protocol", "interface",
                      "function", "method", "class", "object", "variable", "constant",
                      "module", "package", "library", "framework", "architecture",
                      "system", "application", "service", "component", "feature",
                      "movie", "film", "character", "plot", "story", "director",
                      "actor", "actress", "scene", "sequence", "theme", "genre",
                      "cinema", "cinematic", "visual", "special effects", "soundtrack",
                      "score", "editing", "cinematography", "production", "director",
                      "writer", "screenplay", "script", "dialogue", "monologue",
                      "performance", "acting", "role", "character", "protagonist",
                      "antagonist", "supporting", "cast", "crew", "production",
                      "budget", "box office", "revenue", "release", "premiere",
                      "theater", "cinema", "audience", "review", "critic",
                      "rating", "award", "nomination", "academy", "oscar",
                      "golden globe", "bafta", "cannes", "venice", "berlin",
                      "sundance", "tribeca", "independent", "studio", "production",
                      "company", "distributor", "marketing", "promotion", "trailer",
                      "teaser", "poster", "artwork", "design", "concept",
                      "development", "pre-production", "production", "post-production",
                      "editing", "sound", "music", "visual effects", "special effects",
                      "stunts", "action", "drama", "comedy", "thriller", "horror",
                      "sci-fi", "fantasy", "romance", "documentary", "animation",
                      "live action", "3D", "IMAX", "format", "resolution",
                      "aspect ratio", "soundtrack", "score", "song", "music",
                      "sound design", "mixing", "editing", "color", "grading",
                      "visual effects", "special effects", "stunts", "action",
                      "drama", "comedy", "thriller", "horror", "sci-fi", "fantasy",
                      "romance", "documentary", "animation", "live action", "3D",
                      "IMAX", "format", "resolution", "aspect ratio", "soundtrack",
                      "score", "song", "music", "sound design", "mixing", "editing",
                      "color", "grading", "visual effects", "special effects",
                      "stunts", "action", "drama", "comedy", "thriller", "horror",
                      "sci-fi", "fantasy", "romance", "documentary", "animation",
                      "live action", "3D", "IMAX", "format", "resolution",
                      "aspect ratio", "soundtrack", "score", "song", "music",
                      "sound design", "mixing", "editing", "color", "grading"]
    has_technical_terms = any(term in response_lower for term in technical_terms)
    
    # A response is considered factual if it contains fact keywords or technical terms
    # AND is not too long (to avoid storing full conversations)
    is_concise = len(response.split()) <= 100  # Increased word limit
    
    return (has_fact_keywords or has_technical_terms) and is_concise

def extract_context(user_input: str, ai_response: str) -> str:
    """Extract meaningful context from the conversation using sophisticated pattern matching."""
    # Combine user input and AI response for analysis
    combined = f"{user_input} {ai_response}".lower()
    
    # Define context categories with their patterns
    context_patterns = {
        "Technical Fact": [
            # Technical definitions
            r"(?:it|this|that|they|he|she)\s+(?:is|are|was|were|means|refers to)\s+(?:a|an|the)?\s*([^.!?]+(?:system|architecture|framework|technology|method|process)[^.!?]+[.!?])",
            # Technical characteristics
            r"(?:the|a|an)\s+([^.!?]+(?:is|are|was|were)\s+(?:used for|designed to|implemented as|configured to)[^.!?]+[.!?])",
            # Technical relationships
            r"(?:it|this|that|they|he|she)\s+(?:connects|integrates|interacts|communicates)\s+(?:with|to|through)\s+([^.!?]+[.!?])"
        ],
        "Project Context": [
            # Project structure
            r"(?:the|this|that)\s+(?:project|system|application)\s+(?:has|contains|includes|consists of)\s+([^.!?]+[.!?])",
            # Project requirements
            r"(?:we|they|he|she)\s+(?:need|require|must have)\s+([^.!?]+[.!?])",
            # Project constraints
            r"(?:the|this|that)\s+(?:project|system|application)\s+(?:must|should|needs to)\s+([^.!?]+[.!?])"
        ]
    }
    
    # Try each pattern type
    for context_type, patterns in context_patterns.items():
        for pattern in patterns:
            matches = re.finditer(pattern, combined)
            for match in matches:
                context = match.group(1).strip()
                # Validate context quality
                if is_valid_context(context):
                    return f"{context_type}: {context}"
    
    return None

def is_valid_context(context: str) -> bool:
    """Validate if the extracted context is meaningful and complete."""
    # Check minimum length (at least 3 words)
    if len(context.split()) < 3:
        return False
    
    # Check for proper sentence ending
    if not context.endswith(('.', '!', '?')):
        return False
    
    # Check for common meaningless patterns
    meaningless_patterns = [
        r"^\s*(?:i|you|he|she|they|it|this|that|these|those)\s+(?:am|is|are|was|were)\s+(?:a|an|the)\s*$",
        r"^\s*(?:i|you|he|she|they|it|this|that|these|those)\s+(?:am|is|are|was|were)\s*$",
        r"^\s*(?:i|you|he|she|they|it|this|that|these|those)\s+(?:have|has|had)\s*$",
        r"^\s*(?:i|you|he|she|they|it|this|that|these|those)\s+(?:want|need|like|love)\s*$"
    ]
    
    for pattern in meaningless_patterns:
        if re.match(pattern, context, re.IGNORECASE):
            return False
    
    # Check for minimum information content
    # Count significant words (excluding common words)
    common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
    words = set(context.lower().split())
    significant_words = words - common_words
    
    if len(significant_words) < 2:
        return False
    
    return True

def query_llama(prompt):
    """Process user query and maintain session context."""
    try:
        # Add user message to context
        add_message("user", prompt)
        
        # Get stored context
        messages = get_messages()
        
        # Prepare conversation history with system message
        conversation = [
            {
                "role": "system",
                "content": "You are a concise assistant. Keep responses brief and to the point. Use short sentences and avoid unnecessary details."
            }
        ]
        
        # Add conversation history
        for msg in messages:
            conversation.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        # Get response from LLaMA with context
        response = client.chat.completions.create(
            messages=conversation,
            model="llama-3.1-8b-instant",
            temperature=0.7,
            max_tokens=256,  # Reduced from 1024 to 256
        )
        reply = response.choices[0].message.content

        # Store AI response
        add_message("assistant", reply)

        return reply
        
    except Exception as e:
        return f"Error: {str(e)}"

def delete_memory_by_id(msg_id):
    """Delete a specific message from the session."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if it's a fact
    cursor.execute("SELECT is_fact FROM context WHERE id = ?", (msg_id,))
    result = cursor.fetchone()
    if result and result[0]:
        # Remove from facts table
        cursor.execute("DELETE FROM facts WHERE id = ?", (msg_id,))
    
    # Remove from context
    cursor.execute("DELETE FROM context WHERE id = ?", (msg_id,))
    conn.commit()
    conn.close()
    
    console.print(f"[green]Deleted message with ID {msg_id}[/green]")

def show_memory():
    """
    Show all messages with IDs in console.
    """
    messages = get_messages()
    if not messages:
        console.print("[italic dim]No memory stored yet.[/italic dim]")
        return
    for i, msg in enumerate(messages, 1):
        console.print(f"[bold]{i}. [ID: {msg['id']}] [{msg['role'].upper()}][/bold] {msg['content']}")

def tag_filter(keyword):
    """
    Filter messages by keyword in content (case-insensitive).
    """
    messages = get_messages()
    matched = [m for m in messages if keyword.lower() in m["content"].lower()]
    if not matched:
        console.print(f"[italic]No messages containing: '{keyword}'[/italic]")
        return
    for i, msg in enumerate(matched, 1):
        console.print(f"[bold]{i}. [ID: {msg['id']}] [{msg['role'].upper()}][/bold] {msg['content']}")

def print_help():
    """
    Print help menu.
    """
    help_text = """
    [bold]/help[/bold] - Show this help menu.
    [bold]/memory[/bold] - Show stored memory messages.
    [bold]/delete <message_id>[/bold] - Delete a specific memory message by its ID.
    [bold]/reset[/bold] - Clear all memory.
    [bold]/exit[/bold] - Save all messages to GitHub and exit the program.
    """
    console.print(help_text)

def exit_session():
    """Exit the session and push all messages to GitHub."""
    try:
        # Get all messages from the database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, role, content 
            FROM context 
            ORDER BY timestamp DESC
        """)
        messages = [{"id": _id, "role": role, "content": content} 
                for _id, role, content in cursor.fetchall()]
        conn.close()
        
        if not messages:
            console.print("[yellow]No messages to save.[/yellow]")
            return
        
        console.print(f"[green]Saving {len(messages)} messages to GitHub...[/green]")
        
        # Save messages to JSON
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(messages, f, indent=2)
        
        # Push to GitHub
        try:
            # Add the file
            subprocess.run(["git", "add", JSON_PATH], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Commit with timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commit_msg = f"Update conversation - {timestamp}"
            subprocess.run(["git", "commit", "-m", commit_msg], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Push changes
            subprocess.run(["git", "push"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            console.print("[green]Successfully saved conversation to GitHub[/green]")
            
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to push to GitHub: {e}[/red]")
            # If push fails, try to pull first and then push again
            try:
                subprocess.run(["git", "pull", "--rebase"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["git", "push"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                console.print("[green]Successfully saved conversation to GitHub after resolving conflicts[/green]")
            except subprocess.CalledProcessError as e2:
                console.print(f"[red]Failed to resolve GitHub conflicts: {e2}[/red]")
    except Exception as e:
        console.print(f"[red]Error saving to GitHub: {e}[/red]")
