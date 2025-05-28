from logic import (
    init_db, query_llama, get_messages, get_facts,
    save_session_to_github, pull_json_from_github,
    delete_memory_by_id, clear_session, DB_PATH
)
import sqlite3
import os
import atexit
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
import json
import subprocess

console = Console()

ASCII_ART = """

                                                ███╗   ███╗ ██████╗██████╗     ███████╗██╗███╗   ███╗
                                                ████╗ ████║██╔════╝██╔══██╗    ██╔════╝██║████╗ ████║
                                                ██╔████╔██║██║     ██████╔╝    ███████╗██║██╔████╔██║
                                                ██║╚██╔╝██║██║     ██╔═══╝     ╚════██║██║██║╚██╔╝██║
                                                ██║ ╚═╝ ██║╚██████╗██║         ███████║██║██║ ╚═╝ ██║
                                                ╚═╝     ╚═╝ ╚═════╝╚═╝         ╚══════╝╚═╝╚═╝     ╚═╝
                                                     
"""

def print_facts():
    """Show only factual messages from the current session."""
    facts = get_facts()
    if not facts:
        console.print("[yellow]No facts available in this session.[/yellow]")
        return
    console.print("[bold blue]Current Facts:[/bold blue]")
    for i, msg in enumerate(facts, 1):
        role = "👤" if msg["role"] == "user" else "🤖"
        console.print(f"{i}. {role} {msg['content']} [ID: {msg['id']}]")

def print_session():
    """Show all messages from the current session."""
    messages = get_messages()
    if not messages:
        console.print(Panel("No messages in this session.", style="yellow italic"))
        return
    
    session_text = Text()
    session_text.append("Current Session Messages:\n\n", style="bold blue")
    
    for i, msg in enumerate(messages, 1):
        role = "👤" if msg["role"] == "user" else "🤖"
        fact_marker = "📚" if msg.get("is_fact") else ""
        session_text.append(f"{i}. ", style="bold green")
        session_text.append(f"{role} ", style="bold cyan")
        session_text.append(f"{msg['content']} ", style="white")
        session_text.append(f"{fact_marker} ", style="yellow")
        session_text.append(f"[ID: {msg['id']}]\n", style="dim")
    
    console.print(Panel(session_text, title="Session History", border_style="blue"))

def end_session():
    """Save facts to GitHub and clear session."""
    save_session_to_github()
    clear_session()

def print_help():
    """
    Print help menu.
    """
    help_text = Text()
    help_text.append("Available Commands:\n\n", style="bold cyan")
    help_text.append("• ", style="bold green")
    help_text.append("/help", style="bold yellow")
    help_text.append(" - Show this help menu\n")
    help_text.append("• ", style="bold green")
    help_text.append("/memory", style="bold yellow")
    help_text.append(" - Show stored memory messages\n")
    help_text.append("• ", style="bold green")
    help_text.append("/delete <message_id>", style="bold yellow")
    help_text.append(" - Delete a specific memory message\n")
    help_text.append("• ", style="bold green")
    help_text.append("/delete all", style="bold yellow")
    help_text.append(" - Delete all stored memory\n")
    help_text.append("• ", style="bold green")
    help_text.append("/reset", style="bold yellow")
    help_text.append(" - Clear current session and start fresh\n")
    help_text.append("• ", style="bold green")
    help_text.append("/exit", style="bold yellow")
    help_text.append(" - Exit the program")
    
    console.print(Panel(help_text, title="Help Menu", border_style="cyan"))

def main():
    """Main function to run the chat interface."""
    # Create a styled ASCII art panel
    ascii_panel = Panel(Text(ASCII_ART, style="bold blue"), 
                       title="Welcome to MCP Chat", 
                       border_style="blue")
    console.print(ascii_panel)
    
    # Welcome message in a panel
    welcome_text = Text()
    welcome_text.append("Welcome to the Chat Interface!\n", style="bold green")
    welcome_text.append("Type ", style="white")
    welcome_text.append("/help", style="bold yellow")
    welcome_text.append(" for available commands.", style="white")
    console.print(Panel(welcome_text, border_style="green"))
    
    # Initialize database and start session
    init_db()
    
    while True:
        try:
            user_input = console.input("[bold blue]You:[/bold blue] ")
            
            if user_input.lower() == "/exit":
                # Save session to GitHub before exiting
                save_session_to_github()
                exit_text = Text("Thank you for using MCP Chat!\nGoodbye!", style="bold green")
                console.print(Panel(exit_text, border_style="green"))
                break
                
            elif user_input.lower() == "/help":
                print_help()
                
            elif user_input.lower() == "/memory":
                print_session()
                
            elif user_input.lower() == "/delete all":
                # Delete all messages from current session
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM context")
                cursor.execute("DELETE FROM facts")
                conn.commit()
                conn.close()
                
                # Clear context.json and push to GitHub
                with open("context.json", "w") as f:
                    json.dump([], f)
                try:
                    subprocess.run(["git", "add", "context.json"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    subprocess.run(["git", "commit", "-m", "Clear all memory"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    subprocess.run(["git", "push"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except subprocess.CalledProcessError as e:
                    error_text = Text(f"Failed to update GitHub: {e}", style="bold red")
                    console.print(Panel(error_text, border_style="red"))
                
                success_text = Text("All memory has been deleted from local storage and GitHub.", style="bold green")
                console.print(Panel(success_text, border_style="green"))
                
            elif user_input.lower().startswith("/delete "):
                msg_id = user_input.split(" ")[1]
                delete_memory_by_id(msg_id)
                
            elif user_input.lower() == "/reset":
                clear_session()
                
            else:
                # Process the query and get response
                response = query_llama(user_input)
                response_text = Text()
                response_text.append("Assistant: ", style="bold green")
                response_text.append(response, style="white")
                console.print(Panel(response_text, border_style="green"))
                
        except KeyboardInterrupt:
            # Save session to GitHub before exiting
            save_session_to_github()
            exit_text = Text("Session interrupted.\nGoodbye!", style="bold yellow")
            console.print(Panel(exit_text, border_style="yellow"))
            break
        except Exception as e:
            error_text = Text(f"Error: {str(e)}", style="bold red")
            console.print(Panel(error_text, border_style="red"))

if __name__ == "__main__":
    main()
