import sys
import time
import datetime

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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


class RenderProgressUI:
    def __init__(self, total_frames, encoder_name="FFmpeg", resolution="3840x2160 (4K UHD)", fps_target=60, output_name=""):
        self.total_frames = max(1, total_frames)
        self.encoder_name = encoder_name
        self.resolution = resolution
        self.fps_target = fps_target
        self.output_name = output_name
        
        self.start_time = time.time()
        self.start_datetime = datetime.datetime.now()
        self.current_frame = 0
        self.current_fps = 0.0
        self.current_speed = "0.0x"
        self.status = "running"  # "running", "completed", "cancelled", "error"
        self.status_message = ""
        self.finish_datetime = None
        self.live = None

    def get_renderable(self):
        table = Table.grid(padding=(0, 2))
        table.add_column(justify="left", style="bold cyan")
        table.add_column(justify="left")

        # 1. Status
        if self.status == "running":
            status_text = Text("[EM ANDAMENTO]", style="bold yellow")
        elif self.status == "completed":
            status_text = Text("[CONCLUIDO COM SUCESSO]", style="bold green")
        elif self.status == "cancelled":
            status_text = Text("[CANCELADO PELO USUARIO]", style="bold red")
        else:
            err = f": {self.status_message}" if self.status_message else ""
            status_text = Text(f"[FALHA NA RENDERIZACAO]{err}", style="bold red")
        table.add_row("Status:", status_text)

        # 2. Início da Renderização
        start_str = self.start_datetime.strftime("%d/%m/%Y às %H:%M:%S")
        table.add_row("Início da Renderização:", Text(start_str, style="white"))

        # 3. Encoder / Resolução
        enc_info = f"{self.encoder_name} | {self.resolution} @ {self.fps_target} fps"
        table.add_row("Encoder / Configuração:", Text(enc_info, style="white"))

        # 4. Arquivo de Destino
        if self.output_name:
            out_disp = self.output_name
            if len(out_disp) > 60:
                out_disp = out_disp[:28] + "..." + out_disp[-28:]
            table.add_row("Arquivo de Destino:", Text(out_disp, style="yellow"))

        # 5. Frame em Processamento
        frame_disp = f"{self.current_frame:,} / {self.total_frames:,}".replace(",", ".")
        table.add_row("Frame em Processamento:", Text(f"{frame_disp} frames", style="bold white"))

        # 6. Barra de Progresso e Percentual
        percent = (self.current_frame / self.total_frames) * 100 if self.total_frames > 0 else 0
        percent = min(100.0, max(0.0, percent))
        bar_length = 30
        filled = int(bar_length * (percent / 100.0))
        filled = min(bar_length, max(0, filled))
        bar = f"[deep_pink3]{'━' * filled}[/deep_pink3][grey37]{'━' * (bar_length - filled)}[/grey37]"
        table.add_row("Progresso:", f"{bar}  [bold magenta]{percent:5.1f}%[/bold magenta]")

        # 7. Velocidade de Processamento (FPS e Speed)
        fps_disp = f"{self.current_fps:.1f} fps" if self.current_fps > 0 else "-- fps"
        speed_disp = self.current_speed if self.current_speed and self.current_speed != "N/A" else "--"
        table.add_row("Velocidade de Renderização:", Text(f"{fps_disp}  •  Velocidade: {speed_disp}", style="cyan"))

        # 8. Tempo Decorrido
        end_ref = self.finish_datetime.timestamp() if self.finish_datetime else time.time()
        elapsed = max(0, end_ref - self.start_time)
        el_h = int(elapsed // 3600)
        el_m = int((elapsed % 3600) // 60)
        el_s = int(elapsed % 60)
        elapsed_str = f"{el_h:02d}:{el_m:02d}:{el_s:02d}"
        table.add_row("Tempo Decorrido:", Text(elapsed_str, style="white"))

        # 9. Tempo Restante (ETA) e 10. Previsão de Término
        if self.status == "completed":
            table.add_row("Tempo Restante:", Text("00:00:00 (Concluído)", style="green"))
            fin_str = self.finish_datetime.strftime("%H:%M:%S") if self.finish_datetime else "--:--:--"
            table.add_row("Finalizado às:", Text(fin_str, style="bold green"))
        elif self.status in ("cancelled", "error"):
            table.add_row("Tempo Restante:", Text("--:--:-- (Interrompido)", style="red"))
            table.add_row("Horário de Parada:", Text(datetime.datetime.now().strftime("%H:%M:%S"), style="bold red"))
        else:
            eta = None
            if self.current_fps > 0:
                remaining_frames = max(0, self.total_frames - self.current_frame)
                eta = remaining_frames / self.current_fps
            elif percent > 1.0 and elapsed > 2:
                rate = self.current_frame / elapsed
                if rate > 0:
                    eta = max(0, (self.total_frames - self.current_frame) / rate)

            if eta is not None and eta >= 0:
                eta_h = int(eta // 3600)
                eta_m = int((eta % 3600) // 60)
                eta_s = int(eta % 60)
                eta_str = f"{eta_h:02d}:{eta_m:02d}:{eta_s:02d}"
                prev_time = datetime.datetime.now() + datetime.timedelta(seconds=eta)
                prev_str = prev_time.strftime("%H:%M:%S")
            else:
                eta_str = "Calculando..."
                prev_str = "Calculando..."

            table.add_row("Tempo Restante Previsto:", Text(eta_str, style="bold magenta"))
            table.add_row("Horário Previsto de Término:", Text(prev_str, style="bold cyan"))

        # Cor da borda
        if self.status == "completed":
            border_col = "green"
        elif self.status in ("cancelled", "error"):
            border_col = "red"
        else:
            border_col = "cyan"

        panel = Panel(
            table,
            title="[bold white][4K UHD] ETAPA 2: RENDERIZACAO DE VIDEO (FFMPEG)[/bold white]",
            title_align="left",
            border_style=border_col,
            box=ROUNDED,
            padding=(1, 2),
            expand=False
        )
        return panel

    def start(self):
        self.start_time = time.time()
        self.start_datetime = datetime.datetime.now()
        self.live = Live(self.get_renderable(), refresh_per_second=4, transient=False)
        self.live.start()

    def update(self, frame=None, fps=None, speed=None):
        if frame is not None:
            self.current_frame = frame
        if fps is not None:
            self.current_fps = fps
        if speed is not None:
            self.current_speed = speed
        if self.live:
            self.live.update(self.get_renderable())

    def finish(self, success=True, message=""):
        self.finish_datetime = datetime.datetime.now()
        if success:
            self.status = "completed"
            self.current_frame = self.total_frames
        else:
            self.status = "error"
            self.status_message = message
        if self.live:
            self.live.update(self.get_renderable())
            self.live.stop()
            self.live = None

    def cancel(self):
        self.finish_datetime = datetime.datetime.now()
        self.status = "cancelled"
        if self.live:
            self.live.update(self.get_renderable())
            self.live.stop()
            self.live = None

