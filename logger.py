#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MÓDULO DE LOGS E GERENCIAMENTO DE PROJETOS - TIMELAPSE STUDIO 4K
--------------------------------------------------------------
Gerencia o histórico geral consolidado e os logs específicos de cada etapa
organizados por projeto (identificado pela data/hora da foto mais antiga da fonte).
"""

import os
import datetime
from PIL import Image

LOGS_DIR = "logs"
GENERAL_LOG_FILE = "timelapse_studio.log"

def ensure_logs_dir():
    """Garante a existência do diretório principal de logs."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    return LOGS_DIR

def extract_exif_datetime(img_path):
    """
    Extrai a data/hora original da foto.
    Otimização: Se o nome do arquivo já começar com YYYY-MM-DD_HH-MM-SS_, lê em 0.0001s sem abrir imagem.
    """
    base_name = os.path.basename(img_path)
    if len(base_name) >= 19 and base_name[4] == '-' and base_name[7] == '-' and base_name[10] == '_' and base_name[13] == '-' and base_name[16] == '-':
        try:
            return datetime.datetime.strptime(base_name[:19], '%Y-%m-%d_%H-%M-%S')
        except ValueError:
            pass

    try:
        with Image.open(img_path) as img:
            exif = img._getexif()
            if exif:
                # Tags EXIF: 36867 = DateTimeOriginal, 306 = DateTime, 36868 = DateTimeDigitized
                dt_str = exif.get(36867) or exif.get(306) or exif.get(36868)
                if dt_str and isinstance(dt_str, str):
                    try:
                        return datetime.datetime.strptime(dt_str[:19], '%Y:%m:%d %H:%M:%S')
                    except ValueError:
                        pass
    except Exception:
        pass
    
    try:
        if os.path.exists(img_path):
            mtime = os.path.getmtime(img_path)
            return datetime.datetime.fromtimestamp(mtime)
    except Exception:
        pass
        
    return datetime.datetime.now()

def get_project_id(photos_or_source_dir, output_dir_name="fotos_cortadas_4k"):
    """
    Determina o identificador do projeto no formato YYYY-MM-DD_HH-MM-SS
    com base na data/hora da foto mais antiga encontrada na pasta de origem.
    """
    photo_paths = []
    if isinstance(photos_or_source_dir, list):
        photo_paths = photos_or_source_dir
    elif isinstance(photos_or_source_dir, str) and os.path.exists(photos_or_source_dir):
        valid_exts = {".jpg", ".jpeg"}
        output_dir_abs = os.path.abspath(output_dir_name)
        output_in_base_abs = os.path.abspath(os.path.join(photos_or_source_dir, output_dir_name))
        
        for root, dirs, files in os.walk(photos_or_source_dir):
            abs_root = os.path.abspath(root)
            if abs_root == output_dir_abs or abs_root.startswith(output_dir_abs + os.sep):
                continue
            if abs_root == output_in_base_abs or abs_root.startswith(output_in_base_abs + os.sep):
                continue
            if "__pycache__" in root or ".git" in root:
                continue
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in valid_exts and not f.endswith("_crop4k.jpg"):
                    photo_paths.append(os.path.join(root, f))
    
    if not photo_paths:
        # Fallback para timestamp atual
        return datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        
    oldest_dt = None
    # Verifica as primeiras e últimas fotos ou amostra caso haja milhares
    sample = photo_paths[:50] + photo_paths[-50:] if len(photo_paths) > 100 else photo_paths
    for p in sample:
        dt = extract_exif_datetime(p)
        if oldest_dt is None or dt < oldest_dt:
            oldest_dt = dt
            
    if oldest_dt is None:
        oldest_dt = datetime.datetime.now()
        
    return oldest_dt.strftime('%Y-%m-%d_%H-%M-%S')

def log_event(project_id, stage_name, message, level="INFO", to_general=True):
    """
    Grava um evento no log da etapa específica do projeto e opcionalmente no log geral consolidado.
    stage_name: 'etapa_1_rename', 'etapa_2_crop', 'etapa_3_video', 'etapa_4_clean', 'etapa_5_youtube', 'resumo_projeto'
    """
    ensure_logs_dir()
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{now_str}] [{level.upper()}] {message}\n"
    
    # 1. Log do Projeto Específico
    if project_id:
        proj_dir = os.path.join(LOGS_DIR, project_id)
        os.makedirs(proj_dir, exist_ok=True)
        stage_file = os.path.join(proj_dir, f"{stage_name}.log")
        try:
            with open(stage_file, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception as e:
            print(f"[!] Erro ao gravar log do projeto: {e}")
            
    # 2. Log Geral Consolidado (timelapse_studio.log)
    if to_general:
        general_file = os.path.join(LOGS_DIR, GENERAL_LOG_FILE)
        proj_tag = f"[PROJETO: {project_id}] " if project_id else ""
        gen_line = f"[{now_str}] [{level.upper()}] {proj_tag}{message}\n"
        try:
            with open(general_file, "a", encoding="utf-8") as f:
                f.write(gen_line)
        except Exception as e:
            print(f"[!] Erro ao gravar log geral: {e}")
