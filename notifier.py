#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MÓDULO DE NOTIFICAÇÕES (WINDOWS TOAST & NTFY) - TIMELAPSE STUDIO 4K
------------------------------------------------------------------
Envia notificações locais nativas (Windows Toast) e notificações push remotas (ntfy.sh)
com suporte a emojis, tags, prioridades e botões de ação para links do YouTube.
"""

import os
import sys
import json
import urllib.request
import urllib.error
import subprocess
import threading
import logger

DEFAULT_NTFY_TOPIC = "timelapse-studio-2026"

def send_ntfy_notification(topic=DEFAULT_NTFY_TOPIC, title="Timelapse Studio", message="", tags=None, priority="default", actions=None):
    """
    Envia uma notificação push via HTTP POST para o ntfy.sh.
    Executado de forma assíncrona ou com timeout curto para não travar a aplicação.
    """
    def _do_send():
        url = f"https://ntfy.sh/{topic}"
        headers = {
            "Title": title.encode("utf-8"),
            "Priority": priority,
        }
        if tags:
            if isinstance(tags, list):
                headers["Tags"] = ",".join(tags)
            else:
                headers["Tags"] = str(tags)
                
        if actions:
            # Exemplo de action: "view, Assistir no YouTube, https://youtu.be/..."
            if isinstance(actions, list):
                headers["Actions"] = "; ".join(actions)
            else:
                headers["Actions"] = str(actions)
                
        try:
            req = urllib.request.Request(
                url,
                data=message.encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                pass
        except Exception as e:
            # Silencioso no terminal para não poluir tela, gravado em log se necessário
            pass

    # Dispara em thread separada para resposta instantânea
    t = threading.Thread(target=_do_send, daemon=True)
    t.start()

def send_windows_toast(title, message, app_id="Timelapse Studio 4K"):
    """
    Emite uma notificação Toast nativa no Windows 10/11 usando PowerShell.
    """
    if sys.platform != "win32":
        return

    def _do_toast():
        # Limpa aspas para não quebrar a string do PowerShell
        safe_title = title.replace('"', '`"').replace("'", "''")
        safe_msg = message.replace('"', '`"').replace("'", "''")
        safe_app = app_id.replace('"', '`"').replace("'", "''")

        ps_script = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $textNodes = $template.GetElementsByTagName("text")
        $textNodes.Item(0).AppendChild($template.CreateTextNode("{safe_title}")) > $null
        $textNodes.Item(1).AppendChild($template.CreateTextNode("{safe_msg}")) > $null
        $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{safe_app}")
        $notifier.Show($toast)
        """
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5
            )
        except Exception:
            pass

    t = threading.Thread(target=_do_toast, daemon=True)
    t.start()

def notify_stage_completion(project_id, stage_number, stage_name, details="", youtube_url=None, ntfy_topic=DEFAULT_NTFY_TOPIC):
    """
    Centraliza o envio conjunto da notificação Toast no Windows e Push no NTFY ao concluir uma etapa.
    """
    stage_icons = {
        1: ("camera", "Etapa 1 Concluída: Fotos Organizadas"),
        2: ("scissors", "Etapa 2 Concluída: Fotos Cortadas 4K"),
        3: ("film_projector", "Etapa 3 Concluída: Vídeo 4K Gerado"),
        4: ("wastebasket", "Etapa 4 Concluída: Fotos Cortadas Limpas"),
        5: ("youtube", "Etapa 5 Concluída: Publicado no YouTube"),
    }
    
    tag, stage_title = stage_icons.get(stage_number, ("white_check_mark", f"Etapa {stage_number} Concluída"))
    toast_title = f"Timelapse Studio - Etapa {stage_number} Concluída"
    toast_message = f"Projeto: {project_id}\n{details}" if details else f"Projeto: {project_id}\n{stage_name} concluída com sucesso."
    
    # 1. Notificação Windows Toast
    send_windows_toast(toast_title, toast_message)
    
    # 2. Notificação NTFY
    ntfy_tags = [tag, "white_check_mark"]
    actions = None
    if youtube_url:
        actions = [f"view, Assistir no YouTube, {youtube_url}"]
        ntfy_tags.append("tv")
        
    ntfy_body = f"📁 Projeto: {project_id}\n⚙️ {stage_name}\n📊 {details}"
    if youtube_url:
        ntfy_body += f"\n\n🔗 Link: {youtube_url}"
        
    send_ntfy_notification(
        topic=ntfy_topic,
        title=f"🎬 Timelapse Studio: {stage_title}",
        message=ntfy_body,
        tags=ntfy_tags,
        priority="high" if stage_number in [3, 5] else "default",
        actions=actions
    )
