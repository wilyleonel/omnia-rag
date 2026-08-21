from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.align import Align
from rich.text import Text
from rich.live import Live
from rich.box import ROUNDED
import time

class Dashboard:
    def __init__(self):
        self.console = Console()
        self.stats = {
            "documents": 0,
            "chunks": 0,
            "queries_today": 0,
            "avg_context_k": 0.0,
            "tokens_avoided": 0,
            "savings_usd": 0.0
        }

    def generate_layout(self):
        layout = Layout()
        
        # Header
        header = Panel(Align.center(Text("OMNIA-RAG DASHBOARD 🧠⚡", style="bold cyan")), box=ROUNDED, style="blue")
        
        # Stats Table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="bold white", justify="right")
        
        table.add_row("Documentos Indexados:", str(self.stats["documents"]))
        table.add_row("Chunks Vectoriales:", str(self.stats["chunks"]))
        table.add_row("", "")
        table.add_row("Consultas (Hoy):", str(self.stats["queries_today"]))
        table.add_row("Contexto Promedio:", f"{self.stats['avg_context_k']:.1f}K tokens")
        table.add_row("", "")
        table.add_row("[green]Tokens Ahorrados:[/green]", f"[bold green]{self.stats['tokens_avoided']:,}[/bold green]")
        table.add_row("[green]Ahorro Estimado ($):[/green]", f"[bold green]${self.stats['savings_usd']:.4f}[/bold green]")
        
        body = Panel(table, title="Estadísticas en Tiempo Real", box=ROUNDED)
        
        layout.split(
            Layout(header, size=3),
            Layout(body)
        )
        return layout

    def update_stats(self, **kwargs):
        for k, v in kwargs.items():
            if k in self.stats:
                self.stats[k] = v
                
        # Calcular ahorros automáticamente (ej. $3 por cada millón de tokens de Claude 3.5 Sonnet)
        self.stats["savings_usd"] = (self.stats["tokens_avoided"] / 1_000_000) * 3.0

    def render(self):
        return self.generate_layout()

if __name__ == "__main__":
    # Test del dashboard
    dash = Dashboard()
    dash.update_stats(documents=1284, chunks=18932, queries_today=47, avg_context_k=2.1, tokens_avoided=38700)
    with Live(dash.render(), refresh_per_second=1, screen=True):
        time.sleep(5)
