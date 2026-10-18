import json
import os
from rich.console import Console
from rich.prompt import Prompt, IntPrompt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NICHES_FILE = os.path.join(BASE_DIR, "niches.json")
CONFIG_FILE = os.path.join(BASE_DIR, "niche_config.json")

def select_niche():
    console = Console()
    with open(NICHES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    
    console.print("\n[bold cyan]🎬 SELECT YOUR NICHE[/bold cyan]\n")
    for i, cat in enumerate(data["categories"], 1):
        console.print(f"  [yellow]{i}.[/yellow] {cat['name']}")
    
    choice = IntPrompt.ask("\n[bold green]Enter category number[/bold green]", default=1)
    if choice < 1 or choice > len(data["categories"]):
        console.print("[red]Invalid choice[/red]")
        return None
        
    cat = data["categories"][choice - 1]
    console.print(f"\n[bold green]✓ Selected: {cat['name']}[/bold green]")
    
    cfg = {
        "niche_id": cat["id"],
        "niche_name": cat["name"],
        "voice": cat["voice"],
        "image_style": cat["image_style"],
        "topics": cat["topics"]
    }
    
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    
    console.print(f"[dim]Saved to {CONFIG_FILE}[/dim]\n")
    return cfg

if __name__ == "__main__":
    select_niche()
