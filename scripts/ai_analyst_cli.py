#!/usr/bin/env python3
"""
AI Trading Analyst - Interactive CLI

Natural language interface for market analysis powered by:
- Massive.com institutional data
- Claude 4 advanced reasoning
- MarketPulse technical analysis

Usage:
    python scripts/ai_analyst_cli.py

Environment Variables:
    MASSIVE_API_KEY - Your Massive.com API key (required for real-time data)
    ANTHROPIC_API_KEY - Your Anthropic API key (required)
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from loguru import logger

from src.ai.massive_analyst import MassiveAIAnalyst


console = Console()


def display_welcome():
    """Display welcome message"""
    welcome_text = """
# 🤖 AI Trading Analyst

Powered by:
- **Massive.com** - Institutional-grade market data
- **Claude 4** - Advanced AI reasoning
- **MarketPulse** - Technical analysis (divergences, ICT, risk management)

## Commands
- Type your question in natural language
- Use **exit** or **quit** to close
- Use **clear** to reset conversation history
- Use **status** to check system status

## Example Queries
- "How is AAPL performing right now compared to MSFT?"
- "Should I buy Tesla?"
- "Give me entry and exit levels for MNQ futures"
- "Analyze SPY divergences and tell me if it's a good short"
- "What's the best risk-reward setup for NVDA?"

Ask me anything about the markets!
    """

    console.print(Panel(
        Markdown(welcome_text),
        title="[bold green]Welcome[/bold green]",
        border_style="green"
    ))


def display_status(analyst: MassiveAIAnalyst):
    """Display system status"""
    table = Table(title="System Status", show_header=True, header_style="bold cyan")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")

    # Check API keys
    massive_configured = bool(os.getenv('MASSIVE_API_KEY'))
    anthropic_configured = bool(os.getenv('ANTHROPIC_API_KEY'))

    table.add_row(
        "Massive.com API",
        "[green]✓ Configured[/green]" if massive_configured else "[red]✗ Not Configured[/red]"
    )
    table.add_row(
        "Anthropic API",
        "[green]✓ Configured[/green]" if anthropic_configured else "[red]✗ Not Configured[/red]"
    )
    table.add_row(
        "AI Agent",
        "[green]✓ Initialized[/green]" if analyst.agent else "[yellow]Not Initialized[/yellow]"
    )
    table.add_row(
        "Divergence Detection",
        "[green]✓ Enabled[/green]"
    )
    table.add_row(
        "ICT Analysis",
        "[green]✓ Enabled[/green]"
    )
    table.add_row(
        "Risk Management",
        "[green]✓ Enabled[/green]"
    )
    table.add_row(
        "Message History",
        f"{len(analyst.message_history)} messages"
    )

    console.print(table)

    if not massive_configured:
        console.print("\n[yellow]⚠ Warning:[/yellow] Massive.com API key not configured.")
        console.print("Set MASSIVE_API_KEY environment variable for real-time data access.")

    if not anthropic_configured:
        console.print("\n[red]✗ Error:[/red] Anthropic API key not configured.")
        console.print("Set ANTHROPIC_API_KEY environment variable to use the AI analyst.")


async def main():
    """Main CLI loop"""
    display_welcome()

    # Initialize analyst
    try:
        analyst = MassiveAIAnalyst()
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\nPlease set ANTHROPIC_API_KEY environment variable.")
        return

    # Check status
    if not os.getenv('MASSIVE_API_KEY'):
        console.print("\n[yellow]Note:[/yellow] Running without Massive.com API key.")
        console.print("Using Yahoo Finance for market data (free but limited).")
        console.print("Get a Massive.com API key for institutional-grade data: https://massive.com\n")

    # Create agent
    console.print()
    with console.status("[cyan]Initializing AI agent...[/cyan]"):
        await analyst.create_agent()

    console.print("[green]✓[/green] AI agent ready!\n")

    # Main loop
    while True:
        try:
            # Get user input
            console.print()
            question = console.input("[bold yellow]You:[/bold yellow] ")

            # Handle special commands
            if question.lower() in ['exit', 'quit', 'q']:
                console.print("[green]Goodbye! Happy trading! 📈[/green]")
                break

            if question.lower() == 'clear':
                analyst.message_history = []
                console.print("[green]✓[/green] Conversation history cleared")
                continue

            if question.lower() == 'status':
                display_status(analyst)
                continue

            if not question.strip():
                continue

            # Process query
            console.print()
            with console.status("[cyan]Analyzing...[/cyan]"):
                response = await analyst.query(question)

            # Display response
            analyst.display_response(response, title="AI Trading Analyst")

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/yellow]")
            console.print("Type 'exit' to quit or continue asking questions.")
            continue

        except Exception as e:
            console.print(f"\n[red]Error:[/red] {e}")
            logger.error(f"CLI error: {e}")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[green]Goodbye![/green]")
