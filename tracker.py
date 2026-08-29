#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MÓDULO DE TRACKING DE ESTADO DO PROJETO - TIMELAPSE STUDIO 4K
------------------------------------------------------------
Gerencia e persiste o status de cada etapa executada para um projeto específico
em logs/<project_id>/status.json.
"""

import os
import json
import datetime
import logger

def get_status_file_path(project_id):
    """Retorna o caminho do arquivo status.json para um projeto."""
    logger.ensure_logs_dir()
    proj_dir = os.path.join(logger.LOGS_DIR, project_id)
    os.makedirs(proj_dir, exist_ok=True)
    return os.path.join(proj_dir, "status.json")

def load_project_status(project_id):
    """
    Carrega o status do projeto.
    Retorna um dicionário com os dados das etapas.
    """
    status_path = get_status_file_path(project_id)
    if os.path.exists(status_path):
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.log_event(project_id, "resumo_projeto", f"Erro ao ler status.json: {e}", level="WARN")
            
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return {
        "project_id": project_id,
        "created_at": now_str,
        "last_updated": now_str,
        "stages": {}
    }

def save_project_status(project_id, status_data):
    """Salva o dicionário de status do projeto em status.json."""
    status_path = get_status_file_path(project_id)
    try:
        status_data["last_updated"] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(status_data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.log_event(project_id, "resumo_projeto", f"Erro ao salvar status.json: {e}", level="ERROR")
        return False

def update_stage_status(project_id, stage_key, status, details=None, extra_data=None):
    """
    Atualiza o status de uma etapa específica ('in_progress', 'completed', 'failed', 'skipped').
    stage_key: 'etapa_1', 'etapa_2', 'etapa_3', 'etapa_4', 'etapa_5'
    """
    status_data = load_project_status(project_id)
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    stage_info = status_data["stages"].get(stage_key, {})
    stage_info["status"] = status
    stage_info["updated_at"] = now_str
    
    if status == "in_progress" and "started_at" not in stage_info:
        stage_info["started_at"] = now_str
    elif status == "completed":
        stage_info["completed_at"] = now_str
        
    if details:
        stage_info["details"] = details
        
    if extra_data and isinstance(extra_data, dict):
        stage_info.update(extra_data)
        
    status_data["stages"][stage_key] = stage_info
    save_project_status(project_id, status_data)

def is_stage_completed(project_id, stage_key):
    """Verifica se uma etapa específica já foi marcada como 'completed' no status.json."""
    status_data = load_project_status(project_id)
    stages = status_data.get("stages", {})
    return stages.get(stage_key, {}).get("status") == "completed"

def get_stage_info(project_id, stage_key):
    """Retorna os dados registrados para uma etapa específica."""
    status_data = load_project_status(project_id)
    return status_data.get("stages", {}).get(stage_key, {})

def get_completed_stages_summary(project_id):
    """
    Retorna uma string resumida das etapas já concluídas para exibição no banner.
    Ex: "[1] [2] [3]" ou "[Nenhuma etapa concluída]"
    """
    status_data = load_project_status(project_id)
    stages = status_data.get("stages", {})
    completed = []
    
    stage_map = [
        ("etapa_1", "1"),
        ("etapa_2", "2"),
        ("etapa_3", "3"),
        ("etapa_4", "4"),
        ("etapa_5", "5")
    ]
    
    for key, num in stage_map:
        if stages.get(key, {}).get("status") == "completed":
            completed.append(f"[{num}]")
            
    if completed:
        return " ".join(completed)
    return "Nenhuma etapa realizada ainda"
