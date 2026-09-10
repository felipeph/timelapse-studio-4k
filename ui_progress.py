import time
import datetime
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.console import Group
from rich.box import ROUNDED

def format_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB")
    i = 0
    while size_bytes >= 1024 and i < len(size_name) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f} {size_name[i]}"

class WorkflowProgress:
    def __init__(self, stage_name, operation_name, total_items, total_bytes, is_bytes=False):
        """
        :param stage_name: Ex: "ETAPA 1: INGESTÃO E VALIDAÇÃO (SD -> SSD)"
        :param operation_name: Ex: "Ingestão SD -> SSD"
        :param total_items: Quantidade total (arquivos ou bytes dependendo de is_bytes)
        :param total_bytes: Volume total em bytes para exibir no cabeçalho
        :param is_bytes: Se True, o progresso principal é medido em Bytes
        """
        self.stage_name = stage_name
        self.operation_name = operation_name
        self.total_items = total_items
        self.total_bytes = total_bytes
        self.is_bytes = is_bytes
        self.start_time = time.time()
        self.start_time_str = datetime.datetime.now().strftime("%H:%M:%S")
        self.current_item_name = ""
        self.current_progress = 0
        self.live = None
        self.speed = 0.0

    def get_renderable(self):
        # Build the panel
        panel_content = Table.grid(padding=(0, 1))
        panel_content.add_row(Text("• Início: ", style="bold green"), Text(self.start_time_str))
        if not self.is_bytes:
            panel_content.add_row(Text("• Arquivos: ", style="bold cyan"), Text(f"{self.total_items:,}".replace(",", ".")))
        else:
            panel_content.add_row(Text("• Arquivos: ", style="bold cyan"), Text("N/A"))
            
        panel_content.add_row(Text("• Volume: ", style="bold yellow"), Text(format_size(self.total_bytes)))
        
        panel = Panel(
            panel_content, 
            title=Text(self.stage_name, style="bold"), 
            title_align="left", 
            border_style="blue", 
            box=ROUNDED,
            expand=False,
            padding=(1, 2)
        )

        # Build the progress section
        details_table = Table.grid(padding=(0, 2))
        details_table.add_column(justify="left", style="bold blue") # Labels
        details_table.add_column(justify="left") # Values

        details_table.add_row("Operacao:", self.operation_name)
        
        item_disp = self.current_item_name
        if len(item_disp) > 50:
            item_disp = item_disp[:47] + "..."
        details_table.add_row("Arquivo atual:", Text(item_disp, style="yellow"))

        # Progress calculation
        percent = (self.current_progress / self.total_items) * 100 if self.total_items > 0 else 100
        percent = min(100.0, percent)
        
        # Progress Bar visual
        bar_length = 30
        filled = int(bar_length * (self.current_progress / self.total_items)) if self.total_items > 0 else bar_length
        filled = min(bar_length, filled)
        
        bar = f"[deep_pink3]{'━' * filled}[/deep_pink3][grey37]{'━' * (bar_length - filled)}[/grey37]"
        
        if self.is_bytes:
            prog_text = f"{percent:.1f}% ({format_size(self.current_progress)} / {format_size(self.total_items)})"
            speed_text = f"{format_size(self.speed)}/s"
        else:
            prog_text = f"{percent:.1f}% ({int(self.current_progress):,} / {self.total_items:,})".replace(",", ".")
            speed_text = f"{self.speed:.1f} it/s"
            
        details_table.add_row("Progresso:", f"{bar} {prog_text}")
        details_table.add_row("Velocidade:", Text(speed_text, style="cyan"))
        
        elapsed = time.time() - self.start_time
        elapsed_h = int(elapsed // 3600)
        elapsed_m = int((elapsed % 3600) // 60)
        elapsed_s = int(elapsed % 60)
        if elapsed_h > 0:
            elapsed_str = f"{elapsed_h}:{elapsed_m:02d}:{elapsed_s:02d}"
        else:
            elapsed_str = f"0:{elapsed_m:02d}:{elapsed_s:02d}"
        
        if self.speed > 0:
            eta = (self.total_items - self.current_progress) / self.speed
            eta = max(0, eta)
            eta_h = int(eta // 3600)
            eta_m = int((eta % 3600) // 60)
            eta_s = int(eta % 60)
            if eta_h > 0:
                eta_str = f"{eta_h}:{eta_m:02d}:{eta_s:02d}"
            else:
                eta_str = f"0:{eta_m:02d}:{eta_s:02d}"
                
            end_time = datetime.datetime.now() + datetime.timedelta(seconds=eta)
            previsao_str = end_time.strftime("%H:%M:%S")
        else:
            eta_str = "--:--"
            previsao_str = "--:--"

        details_table.add_row("Tempo decorrido:", elapsed_str)
        details_table.add_row("Tempo restante:", Text(eta_str, style="magenta bold"))
        details_table.add_row("Previsao fim:", Text(previsao_str, style="cyan bold"))

        return Group(panel, details_table)

    def start(self):
        self.start_time = time.time()
        self.live = Live(self.get_renderable(), refresh_per_second=4, transient=False)
        self.live.start()
        
    def update(self, advance=1, current_item=""):
        if current_item:
            self.current_item_name = current_item
        self.current_progress += advance
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            self.speed = self.current_progress / elapsed
            
        if self.live:
            self.live.update(self.get_renderable())

    def update_exact(self, current_progress, current_item=""):
        if current_item:
            self.current_item_name = current_item
        self.current_progress = current_progress
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            self.speed = self.current_progress / elapsed
            
        if self.live:
            self.live.update(self.get_renderable())

    def stop(self):
        if self.live:
            self.live.update(self.get_renderable())
            self.live.stop()
            self.live = None
