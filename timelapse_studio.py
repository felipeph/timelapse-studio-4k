#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TIMELAPSE STUDIO 4K UHD
-----------------------
Automação completa para processamento de fotos de qualquer câmera (GoPro, Canon SX50, Nikon, Sony, etc.)
em subpastas de DCIM ou no diretório de trabalho/pasta personalizada.

Etapa 1: Recorte centralizado 16:9 (se necessário) e redimensionamento para 4K UHD (3840x2160)
         usando PIL com multiprocessamento, preservando metadados EXIF e nome com sufixo.
Etapa 2: Renderização de vídeo H.264/HEVC ultra-rápida com detecção automática de GPU/CPU,
         nomenclatura cronológica dinâmica (YYYY-MM-DD_HH-MM---HH-MM) e injeção de metadados.

Interface de Linha de Comando (CLI) Interativa com Ajuste Rápido de FPS, Pasta de Origem e Nomenclatura.
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import glob
import time
import json
import argparse
import datetime
import subprocess
import urllib.request
import urllib.parse
import concurrent.futures
from PIL import Image, ExifTags

import logger
import youtube_uploader
import tracker
import notifier

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")

# Configurações Padrão
DEFAULT_CONFIG = {
    "source_dir": ".",
    "target_width": 3840,
    "target_height": 2160,
    "fps": 60,
    "frames_per_image": 1,
    "crf": 15,
    "preset": "ultrafast",
    "crop_mode": "bottom",
    "output_dir": "fotos_cortadas_4k",
    "output_video": "timelapse_4k_cortado.mp4",
    "test_sample_size": 120,
    "test_output_video": "timelapse_teste_4k.mp4",
    "auto_clean_crops": False,
    "youtube_auto_upload": True,
    "youtube_privacy_status": "unlisted",
    "youtube_category_id": "22",
    "youtube_custom_tags": [],
    "stage_interval_seconds": 180,
    "ntfy_topic": "timelapse-studio-2026"
}

def load_config(config_path=CONFIG_FILE):
    """
    Carrega as configurações a partir do arquivo JSON.
    Mescla com DEFAULT_CONFIG para garantir que todas as chaves existam.
    Retorna (config_dict, bool_existia).
    """
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                saved_config = json.load(f)
            if isinstance(saved_config, dict):
                config.update(saved_config)
                return config, True
        except Exception as e:
            print(f"[!] Erro ao ler '{config_path}': {e}. Usando valores padrão.")
            return config, False
    return config, False

def save_config(config, config_path=CONFIG_FILE):
    """
    Salva o dicionário de configurações em formato JSON indentado.
    """
    try:
        keys_to_save = [
            "source_dir", "output_dir", "fps", "frames_per_image", 
            "crop_mode", "crf", "preset", "target_width", 
            "target_height", "test_sample_size", "output_video", "test_output_video",
            "auto_clean_crops", "youtube_auto_upload", "youtube_privacy_status", "youtube_category_id",
            "youtube_custom_tags", "stage_interval_seconds", "ntfy_topic"
        ]
        save_dict = {k: config[k] for k in keys_to_save if k in config}
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(save_dict, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[!] Erro ao salvar configurações em '{config_path}': {e}")
        return False

def interactive_initial_setup_wizard(config_path=CONFIG_FILE):
    """
    Assistente de primeira execução para criar o arquivo config.json
    quando ele não existir.
    """
    print("\n" + "=" * 66)
    print("      BEM-VINDO AO TIMELAPSE STUDIO 4K UHD - CONFIGURAÇÃO INICIAL")
    print("=" * 66)
    print(f" Arquivo de configuração '{config_path}' não encontrado.")
    print(" Vamos definir as preferências padrão para seus projetos!")
    print(" Dica: Pressione [ENTER] em qualquer campo para aceitar o valor padrão.")
    print("-" * 66)
    
    config = DEFAULT_CONFIG.copy()
    
    # 1. Pasta de origem
    src_input = input(f"\n1. Pasta de Origem das Fotos [{config['source_dir']}]: ").strip()
    if src_input:
        sanitized = sanitize_path(src_input)
        if sanitized:
            config["source_dir"] = sanitized
            
    # 2. FPS
    fps_input = input(f"2. Taxa de Quadros por Segundo (FPS) [{config['fps']}]: ").strip()
    if fps_input.isdigit() and int(fps_input) > 0:
        config["fps"] = int(fps_input)
        
    # 3. Frames por Imagem (FPI)
    fpi_input = input(f"3. Frames por Foto (FPI - ex: 1 = rápido, 60 = 1s/foto a 60fps) [{config['frames_per_image']}]: ").strip()
    if fpi_input.isdigit() and int(fpi_input) > 0:
        config["frames_per_image"] = int(fpi_input)
        
    # 4. Modo de corte (Crop)
    print("4. Modo de Enquadramento 16:9 vertical:")
    print("   [1] Base / Por Baixo (Preserva base, apaga topo - Padrão)")
    print("   [2] Centro (Corta topo e base igualmente)")
    print("   [3] Topo (Preserva topo, apaga base)")
    crop_choice = input(f"   Escolha [1/2/3 ou Enter para Base]: ").strip()
    if crop_choice == "2":
        config["crop_mode"] = "center"
    elif crop_choice == "3":
        config["crop_mode"] = "top"
    else:
        config["crop_mode"] = "bottom"
        
    # 5. CRF
    crf_input = input(f"5. Fator de Qualidade CRF (Menor = melhor qualidade, padrão: 15) [{config['crf']}]: ").strip()
    if crf_input.isdigit():
        config["crf"] = int(crf_input)
        
    # 6. Preset
    preset_input = input(f"6. Preset FFmpeg (ultrafast / medium / slow) [{config['preset']}]: ").strip().lower()
    if preset_input in ["ultrafast", "medium", "slow"]:
        config["preset"] = preset_input

    # Salva
    if save_config(config, config_path):
        print(f"\n[+] Configurações iniciais salvas com sucesso em '{config_path}'!")
    else:
        print(f"\n[!] Aviso: Não foi possível gravar '{config_path}'. Usando configurações em memória.")
        
    print("=" * 66)
    time.sleep(1.5)
    return config

CROP_MODE_LABELS = {
    "center": "Centro (Corta topo e base igualmente)",
    "bottom": "Por Baixo (Preserva base, apaga topo)",
    "top": "Por Cima (Preserva topo, apaga base)"
}

def sanitize_path(path_str):
    """Sanitiza caminhos informados pelo usuário, removendo aspas e expandindo ~."""
    if not path_str:
        return ""
    cleaned = path_str.strip().strip("'\"")
    cleaned = os.path.expanduser(cleaned)
    return os.path.normpath(cleaned)

def resolve_custom_video_path(custom_path):
    """
    Resolve e valida o caminho de um vídeo fornecido pelo usuário.
    Suporta:
      - Caminho direto para o arquivo .mp4 (com ou sem aspas)
      - Caminho sem extensão .mp4 (se existir nome.mp4)
      - Caminho para uma pasta (detecta arquivos .mp4 dentro dela automaticamente)
    Retorna o caminho absoluto do arquivo .mp4 selecionado ou None se cancelado/não encontrado.
    """
    if not custom_path:
        return None
        
    cleaned = sanitize_path(custom_path)
    if not cleaned:
        return None

    # Se o caminho não existe diretamente, tenta com a extensão .mp4
    if not os.path.exists(cleaned) and os.path.exists(cleaned + ".mp4"):
        cleaned = cleaned + ".mp4"

    if not os.path.exists(cleaned):
        print(f"[-] Caminho '{cleaned}' não foi encontrado no disco.")
        return None

    # Se for uma pasta, procurar vídeos .mp4 dentro dela
    if os.path.isdir(cleaned):
        dir_name = os.path.basename(cleaned) or cleaned
        print(f"\n[*] Pasta informada: '{dir_name}'")
        print("[*] Buscando arquivos de vídeo .mp4...")
        
        # Busca primeiro na raiz da pasta informada
        mp4_files = sorted(glob.glob(os.path.join(cleaned, "*.mp4")))
        # Se não encontrar na raiz, busca recursivamente nas subpastas
        if not mp4_files:
            mp4_files = sorted(glob.glob(os.path.join(cleaned, "**", "*.mp4"), recursive=True))

        if not mp4_files:
            print(f"[-] Nenhum arquivo .mp4 foi encontrado dentro da pasta '{cleaned}'.")
            return None
        elif len(mp4_files) == 1:
            selected = os.path.abspath(mp4_files[0])
            sz = os.path.getsize(selected) / (1024 * 1024)
            print(f"[+] Vídeo .mp4 detectado automaticamente:")
            print(f"    • {os.path.basename(selected)} ({sz:.2f} MB)")
            return selected
        else:
            print("\n" + "=" * 66)
            print(f"     VÍDEOS .MP4 ENCONTRADOS NA PASTA ({len(mp4_files)} vídeos)")
            print("=" * 66)
            for idx, vf in enumerate(mp4_files, 1):
                sz = os.path.getsize(vf) / (1024 * 1024)
                rel = os.path.relpath(vf, cleaned)
                print(f"  [{idx}] {rel} ({sz:.2f} MB)")
            print("  [0] Digitar outro caminho / Cancelar")
            print("-" * 66)
            choice = input(f"Escolha o vídeo para upload [1-{len(mp4_files)}]: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(mp4_files):
                selected = os.path.abspath(mp4_files[int(choice) - 1])
                print(f"[+] Vídeo selecionado: {os.path.basename(selected)}")
                return selected
            return None

    # Se for um arquivo regular
    if os.path.isfile(cleaned):
        return os.path.abspath(cleaned)
    else:
        print(f"[-] O caminho '{cleaned}' não é um arquivo regular.")
        return None

def get_output_dir(config):
    """
    Retorna o caminho absoluto da pasta de fotos cortadas dentro da pasta de origem.
    Se output_dir já for um caminho absoluto, mantém; caso contrário, une à pasta de origem.
    """
    source_dir = config.get("source_dir", ".")
    output_dir_name = config.get("output_dir", "fotos_cortadas_4k")
    if os.path.isabs(output_dir_name):
        return os.path.abspath(output_dir_name)
    return os.path.abspath(os.path.join(source_dir, output_dir_name))

def print_banner(config=None, project_id=None):
    """Exibe o cabeçalho decorado do programa e as configurações atuais ativas."""
    print("=" * 66)
    print("                TIMELAPSE STUDIO 4K UHD")
    print("   Automação Multicâmeras (GoPro, Canon, etc.) & Renderização")
    print("=" * 66)
    if config:
        if not project_id:
            try:
                project_id = logger.get_project_id(config.get("source_dir", "."), config.get("output_dir", "fotos_cortadas_4k"))
            except Exception:
                project_id = "N/A"
                
        crop_mode = config.get("crop_mode", "bottom")
        crop_label = CROP_MODE_LABELS.get(crop_mode, crop_mode)
        source_dir = config.get("source_dir", ".")
        source_display = os.path.abspath(source_dir) if source_dir else os.getcwd()
        if source_dir == ".":
            source_display += " (Diretório Atual)"
        output_dir_display = get_output_dir(config)
        fps = config.get("fps", 60)
        fpi = config.get("frames_per_image", 1)
        dur_per_photo = fpi / fps if fps > 0 else 0
            
        auto_clean = config.get("auto_clean_crops", False)
        clean_status = "Ativada (Apaga fotos cortadas após renderizar)" if auto_clean else "Desativada"
        yt_auto = config.get("youtube_auto_upload", True)
        yt_privacy = config.get("youtube_privacy_status", "unlisted")
        yt_status = f"Ativado ({yt_privacy})" if yt_auto else "Desativado"
            
        completed_summary = tracker.get_completed_stages_summary(project_id)
        stage_interval = config.get("stage_interval_seconds", 180)
        ntfy_topic = config.get("ntfy_topic", "timelapse-studio-2026")
            
        print(f" PROJETO ATUAL: {project_id}")
        print(f" ETAPAS CONCLUÍDAS: {completed_summary}")
        print("-" * 66)
        print(" CONFIGURAÇÕES ATUAIS:")
        print(f"   • Pasta de Origem (Fotos): {source_display}")
        print(f"   • Pasta de Cortes (4K)   : {output_dir_display}")
        print(f"   • Taxa de Quadros (FPS)  : {fps} fps")
        print(f"   • Frames por Imagem (FPI): {fpi} frame(s)/foto ({dur_per_photo:.2f}s por foto)")
        print(f"   • Modo de Corte (Crop)    : {crop_label}")
        print(f"   • Qualidade (CRF)         : {config['crf']} (Menor = melhor qualidade)")
        print(f"   • Resolução Alvo          : {config['target_width']}x{config['target_height']} (4K UHD)")
        print(f"   • Amostra Modo Teste      : {config['test_sample_size']} fotos")
        print(f"   • Limpeza Pós-Vídeo       : {clean_status}")
        print(f"   • Upload YouTube          : {yt_status}")
        print(f"   • Intervalo entre Etapas  : {stage_interval}s (Pausa interativa)")
        print(f"   • Notificações            : Toast Windows + NTFY ({ntfy_topic})")
        print("=" * 66)

def print_progress_bar(current, total, start_time, prefix="Progresso", current_item=""):
    """Exibe uma barra de progresso formatada com caracteres ASCII seguros no terminal e item atual."""
    percent = current / total if total > 0 else 1.0
    bar_length = 22
    hashes = '=' * int(round(percent * bar_length))
    spaces = '-' * (bar_length - len(hashes))
    
    elapsed = time.time() - start_time
    fps = current / elapsed if elapsed > 0 else 0
    eta = (total - current) / fps if fps > 0 else 0
    
    elapsed_str = time.strftime("%M:%S", time.gmtime(elapsed))
    if elapsed >= 3600:
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
        
    eta_str = time.strftime("%M:%S", time.gmtime(eta))
    if eta >= 3600:
        eta_str = time.strftime("%H:%M:%S", time.gmtime(eta))
        
    item_str = f" | {current_item}" if current_item else ""
    if len(item_str) > 42:
        item_str = item_str[:39] + "..."
        
    sys.stdout.write(
        f"\r{prefix}: [{hashes}{spaces}] {percent*100:.1f}% | "
        f"{current}/{total} | "
        f"{fps:.1f} it/s | "
        f"Tempo: {elapsed_str} | ETA: {eta_str}{item_str}   "
    )
    sys.stdout.flush()

def is_already_formatted_name(filename_or_path):
    """Verifica se o nome do arquivo já segue o padrão YYYY-MM-DD_HH-MM-SS_..."""
    base_name = os.path.basename(filename_or_path)
    name_no_ext, _ = os.path.splitext(base_name)
    if len(name_no_ext) >= 20:
        if (name_no_ext[0:4].isdigit() and name_no_ext[4] == '-' and
            name_no_ext[5:7].isdigit() and name_no_ext[7] == '-' and
            name_no_ext[8:10].isdigit() and name_no_ext[10] == '_' and
            name_no_ext[11:13].isdigit() and name_no_ext[13] == '-' and
            name_no_ext[14:16].isdigit() and name_no_ext[16] == '-' and
            name_no_ext[17:19].isdigit() and name_no_ext[19] == '_'):
            return True
    return False

def get_exif_datetime(img_path):
    """Extrai a data/hora original da foto via cabeçalhos EXIF como objeto datetime."""
    base_name = os.path.basename(img_path)
    if is_already_formatted_name(base_name):
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
    
    # Fallback para timestamp de modificação do arquivo no SO
    try:
        if os.path.exists(img_path):
            mtime = os.path.getmtime(img_path)
            return datetime.datetime.fromtimestamp(mtime)
    except Exception:
        pass
        
    return datetime.datetime.now()

def get_exif_timestamp(img_path):
    """Extrai a data/hora original da foto via cabeçalhos EXIF (suporta GoPro, Canon, etc.)."""
    dt = get_exif_datetime(img_path)
    return dt.strftime('%Y-%m-%d_%H-%M-%S')

def get_photo_camera_info(img_path):
    """
    Extrai modelo da câmera e dimensões originais da foto via EXIF.
    Retorna dicionário com 'camera', 'original_width', 'original_height'.
    """
    info = {"camera": None, "original_width": None, "original_height": None}
    if not img_path or not os.path.exists(img_path):
        return info
    try:
        with Image.open(img_path) as img:
            info["original_width"] = img.width
            info["original_height"] = img.height
            exif = img._getexif()
            if exif:
                # 271: Make, 272: Model
                make = str(exif.get(271, "")).strip() if exif.get(271) else ""
                model = str(exif.get(272, "")).strip() if exif.get(272) else ""
                if make and model:
                    if make.lower() in model.lower():
                        camera_str = model
                    else:
                        camera_str = f"{make} {model}"
                elif model:
                    camera_str = model
                elif make:
                    camera_str = make
                else:
                    camera_str = None
                info["camera"] = camera_str
    except Exception:
        pass
    return info

def parse_datetime_from_video_filename(filename):
    """
    Tenta extrair datas/horas do nome do vídeo gerado pelo Timelapse Studio.
    Suporta:
      timelapse_YYYY-MM-DD_HH-MM---HH-MM.mp4
      timelapse_YYYY-MM-DD_HH-MM---YYYY-MM-DD_HH-MM.mp4
    """
    base = os.path.basename(filename).replace(".mp4", "")
    if "---" in base:
        try:
            parts = base.split("---")
            part1 = parts[0]
            part2 = parts[1]
            
            tokens1 = part1.split("_")
            date1_str = None
            time1_str = None
            for i, t in enumerate(tokens1):
                if len(t) == 10 and t.count("-") == 2:
                    date1_str = t
                    if i + 1 < len(tokens1):
                        time1_str = tokens1[i + 1]
                    break
                    
            date2_str = date1_str
            time2_str = None
            tokens2 = part2.split("_")
            for i, t in enumerate(tokens2):
                if len(t) == 10 and t.count("-") == 2:
                    date2_str = t
                    if i + 1 < len(tokens2):
                        time2_str = tokens2[i + 1]
                    break
                elif len(t) == 5 and t.count("-") == 1:
                    time2_str = t
                    break
                    
            if date1_str and time1_str:
                dt1 = datetime.datetime.strptime(f"{date1_str}_{time1_str}", "%Y-%m-%d_%H-%M")
                if date2_str and time2_str:
                    dt2 = datetime.datetime.strptime(f"{date2_str}_{time2_str}", "%Y-%m-%d_%H-%M")
                else:
                    dt2 = dt1
                return dt1, dt2
        except Exception:
            pass
    return None, None

_GEOCODE_CACHE = {}

def get_photo_gps_coordinates(img_path):
    """
    Extrai coordenadas GPS (latitude, longitude, altitude) dos metadados EXIF da foto.
    Retorna dicionário com {'latitude': float, 'longitude': float, 'altitude': float} ou None.
    """
    if not img_path or not os.path.exists(img_path):
        return None
    try:
        with Image.open(img_path) as img:
            exif = img._getexif()
            if not exif:
                return None
                
            # Tag 34853 = GPSInfo
            gps_info = exif.get(34853) or exif.get(0x8825)
            if not gps_info or not isinstance(gps_info, dict):
                return None
                
            def _to_float(val):
                if isinstance(val, (tuple, list)):
                    return float(val[0]) / float(val[1]) if len(val) == 2 and val[1] != 0 else float(val[0])
                if hasattr(val, 'numerator') and hasattr(val, 'denominator'):
                    return float(val.numerator) / float(val.denominator) if val.denominator != 0 else float(val.numerator)
                return float(val)

            def _convert_dms_to_dd(dms, ref):
                if not dms or len(dms) < 3:
                    return None
                d = _to_float(dms[0])
                m = _to_float(dms[1])
                s = _to_float(dms[2])
                dd = d + (m / 60.0) + (s / 3600.0)
                if ref in ['S', 'W', 's', 'w']:
                    dd = -dd
                return dd

            lat_dms = gps_info.get(2) # GPSLatitude
            lat_ref = gps_info.get(1, 'N') # GPSLatitudeRef
            lon_dms = gps_info.get(4) # GPSLongitude
            lon_ref = gps_info.get(3, 'E') # GPSLongitudeRef
            alt_val = gps_info.get(6) # GPSAltitude
            alt_ref = gps_info.get(5, 0) # GPSAltitudeRef (0 = above sea level, 1 = below)

            if lat_dms and lon_dms:
                latitude = _convert_dms_to_dd(lat_dms, lat_ref)
                longitude = _convert_dms_to_dd(lon_dms, lon_ref)
                altitude = None
                if alt_val is not None:
                    try:
                        altitude = _to_float(alt_val)
                        if alt_ref == 1:
                            altitude = -altitude
                    except Exception:
                        altitude = None

                if latitude is not None and longitude is not None:
                    return {
                        "latitude": round(latitude, 6),
                        "longitude": round(longitude, 6),
                        "altitude": round(altitude, 1) if altitude is not None else None
                    }
    except Exception:
        pass
    return None

def reverse_geocode_coordinates(latitude, longitude, timeout=4.0):
    """
    Realiza o geocoding reverso das coordenadas (lat, lon) usando a API pública OpenStreetMap (Nominatim).
    Retorna dicionário com: city, state, country, formatted_address, display_name.
    """
    key = (round(latitude, 4), round(longitude, 4))
    if key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[key]
        
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={latitude}&lon={longitude}&zoom=14&addressdetails=1"
    headers = {
        "User-Agent": "TimelapseStudio4K/1.0 (Photography Automation Tool)"
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                address = data.get("address", {})
                
                # Extrair cidade / município
                city = (
                    address.get("city") or 
                    address.get("town") or 
                    address.get("municipality") or 
                    address.get("village") or 
                    address.get("suburb") or 
                    address.get("county") or ""
                )
                
                # Extrair estado
                state = address.get("state") or address.get("region") or ""
                
                # Extrair país
                country = address.get("country") or ""
                
                parts = [p for p in [city, state, country] if p]
                formatted = ", ".join(parts) if parts else data.get("display_name", "")
                
                result = {
                    "city": city,
                    "state": state,
                    "country": country,
                    "formatted_address": formatted,
                    "display_name": data.get("display_name", "")
                }
                _GEOCODE_CACHE[key] = result
                return result
    except Exception:
        pass
        
    fallback = {
        "city": "",
        "state": "",
        "country": "",
        "formatted_address": f"{latitude:.5f}, {longitude:.5f}",
        "display_name": ""
    }
    _GEOCODE_CACHE[key] = fallback
    return fallback

def format_photo_name(img_path, dt=None):
    """
    Gera o nome da foto no formato: %Y-%m-%d_%H-%M-%S_<nome_original>.jpg
    Se o arquivo já possuir o prefixo no padrão esperado, mantém imediatamente sem retrabalho.
    """
    base_name = os.path.basename(img_path)
    if is_already_formatted_name(base_name):
        return base_name
        
    if dt is None:
        dt = get_exif_datetime(img_path)
    ts_prefix = dt.strftime('%Y-%m-%d_%H-%M-%S')
    name_no_ext, ext = os.path.splitext(base_name)
    return f"{ts_prefix}_{name_no_ext}{ext.lower()}"

def find_all_photos(base_dir, output_dir_name="fotos_cortadas_4k"):
    """
    Busca todas as fotos JPG/JPEG recursivamente na pasta informada (ex: subpastas DCIM, 138GOPRO, 100CANON, ou raiz),
    ignorando a pasta de saída de cortes e fotos já recortadas.
    """
    image_files = []
    if not base_dir or not os.path.exists(base_dir):
        return []

    output_dir_abs = os.path.abspath(output_dir_name)
    output_in_base_abs = os.path.abspath(os.path.join(base_dir, output_dir_name))
    valid_exts = {".jpg", ".jpeg"}
    
    # Varredura recursiva por todas as subpastas
    for root, dirs, files in os.walk(base_dir):
        # Ignorar pasta de saída cortada, caches e pastas ocultas
        abs_root = os.path.abspath(root)
        if abs_root == output_dir_abs or abs_root.startswith(output_dir_abs + os.sep):
            continue
        if abs_root == output_in_base_abs or abs_root.startswith(output_in_base_abs + os.sep):
            continue
        if "__pycache__" in root or ".git" in root:
            continue
            
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in valid_exts:
                if not file.endswith("_crop4k.jpg") and not file.endswith("_crop4k.jpeg"):
                    image_files.append(os.path.join(root, file))
                
    return sorted(image_files)

# Alias para compatibilidade
find_all_gopro_photos = find_all_photos

def select_source_dir(config):
    """Menu interativo para definir ou alterar a pasta de origem das fotos."""
    current_source = config.get("source_dir", ".")
    current_abs = os.path.abspath(current_source)
    print("\n" + "=" * 66)
    print("            SELEÇÃO DA PASTA DE ORIGEM DAS FOTOS")
    print("=" * 66)
    print(f"Pasta de origem atual: {current_abs}")
    print("\nOpções:")
    print("  [1] Usar diretório de trabalho atual (.)")
    print("  [2] Digitar ou arrastar e soltar (drag & drop) o caminho da pasta...")
    print("  [0] Cancelar / Manter pasta atual")
    print("-" * 66)
    
    choice = input("Escolha uma opção [0-2]: ").strip()
    if choice == "1":
        config["source_dir"] = "."
        photos = find_all_photos(config["source_dir"], config["output_dir"])
        print(f"[+] Pasta de origem redefinida para o diretório atual.")
        print(f"[+] Fotos JPG/JPEG encontradas: {len(photos)}")
    elif choice == "2":
        path_input = input("\nDigite ou arraste a pasta aqui: ").strip()
        cleaned_path = sanitize_path(path_input)
        if not cleaned_path:
            print("[-] Nenhum caminho informado. Mantendo pasta anterior.")
            return
        
        if not os.path.exists(cleaned_path):
            print(f"[-] Erro: O caminho '{cleaned_path}' não foi encontrado.")
            return
        if not os.path.isdir(cleaned_path):
            print(f"[-] Erro: O caminho informado não é uma pasta/diretório válido.")
            return
            
        config["source_dir"] = cleaned_path
        photos = find_all_photos(config["source_dir"], config["output_dir"])
        print(f"[+] Pasta de origem alterada com sucesso para: {os.path.abspath(cleaned_path)}")
        print(f"[+] Total de fotos JPG/JPEG encontradas: {len(photos)}")
    elif choice == "0":
        print("[+] Pasta de origem mantida.")
    else:
        print("[-] Opção inválida. Pasta de origem mantida.")

def process_single_rename(img_path):
    """
    Worker para extrair EXIF e renomear uma foto de origem.
    Retorna (sucesso: bool, old_name: str, new_name: str, motivo: str).
    """
    dir_name = os.path.dirname(img_path)
    old_filename = os.path.basename(img_path)
    try:
        new_filename = format_photo_name(img_path)
        if old_filename != new_filename:
            new_path = os.path.join(dir_name, new_filename)
            if not os.path.exists(new_path):
                os.rename(img_path, new_path)
                return True, old_filename, new_filename, "Renomeado com sucesso"
            else:
                return False, old_filename, new_filename, "Destino já existe"
        return False, old_filename, old_filename, "Já formatado"
    except Exception as e:
        return False, old_filename, old_filename, str(e)

def rename_source_photos(source_dir, output_dir_name="fotos_cortadas_4k", non_interactive=False, project_id=None, config=None):
    """
    Renomeia todas as fotos JPG/JPEG na pasta de origem com a data/hora do EXIF:
    %Y-%m-%d_%H-%M-%S_<nome_original>.jpg
    Exibe barra de progresso em tempo real e nome de cada arquivo.
    """
    if not project_id:
        project_id = logger.get_project_id(source_dir, output_dir_name)
    photos = find_all_photos(source_dir, output_dir_name)
    if not photos:
        print(f"\n[-] Nenhuma foto encontrada em {os.path.abspath(source_dir)} para renomear.")
        return 0
        
    print("\n" + "=" * 66)
    print("      ETAPA 1: ORGANIZAÇÃO E RENOMEAÇÃO DE FOTOS POR EXIF")
    print("=" * 66)
    print(f"[+] Projeto: {project_id}")
    print(f"[+] Pasta de origem: {os.path.abspath(source_dir)}")
    print(f"[+] Total de fotos encontradas: {len(photos)}")
    print("[+] Formato alvo: %Y-%m-%d_%H-%M-%S_<nome_original>.jpg")
    print("-" * 66)
    
    # Verificação rápida se todas as fotos já estão renomeadas (evita retrabalho)
    photos_to_rename = [p for p in photos if not is_already_formatted_name(p)]
    if not photos_to_rename:
        print(f"\n[i] Todas as {len(photos)} fotos já estão no formato padrão por EXIF.")
        print("[+] Nenhuma renomeação necessária. Pulando Etapa 1 (sem retrabalho).")
        print("=" * 66)
        tracker.update_stage_status(project_id, "etapa_1", "completed", details=f"Todas as {len(photos)} fotos já estavam padronizadas")
        logger.log_event(project_id, "etapa_1_rename", f"Todas as {len(photos)} fotos já estavam renomeadas.")
        ntfy_topic = config.get("ntfy_topic", "timelapse-studio-2026") if config else "timelapse-studio-2026"
        notifier.notify_stage_completion(project_id, 1, "Organização e Renomeação EXIF", details=f"Todas as {len(photos)} fotos já estavam organizadas", ntfy_topic=ntfy_topic)
        return 0

    if not non_interactive:
        confirm = input(f"Localizadas {len(photos_to_rename)} fotos para renomear. Prosseguir? (s/N): ").strip().lower()
        if confirm != 's':
            print("[+] Operação cancelada pelo usuário.")
            return 0
            
    tracker.update_stage_status(project_id, "etapa_1", "in_progress")
    renamed_count = 0
    kept_count = len(photos) - len(photos_to_rename)
    errors = 0
    total = len(photos_to_rename)
    start_time = time.time()
    
    # Processamento concorrente para agilizar operações em milhares de fotos
    max_workers = min(32, (os.cpu_count() or 4) * 4)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_single_rename, p) for p in photos_to_rename]
        for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
            success, old_name, new_name, reason = future.result()
            if success:
                renamed_count += 1
                logger.log_event(project_id, "etapa_1_rename", f"Renomeado: {old_name} -> {new_name}", to_general=False)
                item_display = f"{old_name} -> {new_name}"
            else:
                if reason == "Já formatado":
                    kept_count += 1
                else:
                    errors += 1
                    logger.log_event(project_id, "etapa_1_rename", f"Erro em {old_name}: {reason}", level="WARN", to_general=False)
                item_display = f"{old_name} ({reason})"
                
            print_progress_bar(idx, total, start_time, prefix="Renomeando fotos", current_item=item_display)
            
    print() # Pular linha
    total_time = time.time() - start_time
    print("-" * 66)
    print(f"[+] Concluído! {renamed_count} arquivos renomeados, {kept_count} mantidos em {total_time:.1f}s ({total/total_time:.1f} fotos/s).")
    if errors > 0:
        print(f"[!] {errors} arquivos apresentaram erros ou conflitos.")
    print("=" * 66)
    
    # Atualiza tracking e dispara notificações
    tracker.update_stage_status(project_id, "etapa_1", "completed", details=f"{renamed_count} fotos renomeadas, {kept_count} mantidas ({total} fotos totais)")
    logger.log_event(project_id, "etapa_1_rename", f"Etapa 1 finalizada: {renamed_count} fotos renomeadas, {kept_count} mantidas.")
    ntfy_topic = config.get("ntfy_topic", "timelapse-studio-2026") if config else "timelapse-studio-2026"
    notifier.notify_stage_completion(project_id, 1, "Organização e Renomeação EXIF", details=f"{renamed_count} fotos renomeadas ({total} fotos totais)", ntfy_topic=ntfy_topic)
    return renamed_count

def process_single_image(task):
    """
    Worker executado em paralelo para cortar 16:9 (centralizado, por baixo ou por cima)
    e redimensionar/ajustar para a resolução alvo (ex: 3840x2160 4K),
    preservando os metadados EXIF e o nome base com o sufixo _crop4k.jpg.
    Retorna (sucesso: bool, out_path_ou_erro: str, is_reused: bool).
    """
    img_path, output_dir, target_w, target_h, seq_idx, crop_mode = task
    try:
        formatted_name = format_photo_name(img_path)
        name_no_ext, _ = os.path.splitext(formatted_name)
        
        # Nome do arquivo final: %Y-%m-%d_%H-%M-%S_nomeoriginal_crop4k.jpg
        out_filename = f"{name_no_ext}_crop4k.jpg"
        out_path = os.path.join(output_dir, out_filename)
        
        # Evitar retrabalho: se a foto cortada já existe com tamanho válido (> 1KB), reaproveita sem processar!
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1024:
            return True, out_path, True
            
        with Image.open(img_path) as img:
            raw_exif = img.info.get("exif")
            w, h = img.size
            target_aspect = target_w / target_h
            img_aspect = w / h
            
            # Tolerância para considerar a imagem já na proporção correta (ex: 16:9 da Canon SX50)
            if abs(img_aspect - target_aspect) < 0.01:
                crop_w = w
                crop_h = h
                left = 0
                top = 0
            elif img_aspect > target_aspect:
                # Imagem mais larga que 16:9 (ex: panorâmica 21:9)
                crop_w = int(h * target_aspect)
                crop_h = h
                left = (w - crop_w) // 2
                top = 0
            else:
                # Imagem mais alta que 16:9 (ex: 4:3 de GoPro / celulares / câmeras 3:2)
                crop_w = w
                crop_h = int(w / target_aspect)
                excess_h = h - crop_h
                left = 0
                if crop_mode == "top":
                    # Alinhado por cima (preserva topo, apaga base)
                    top = 0
                elif crop_mode == "bottom":
                    # Alinhado por baixo (preserva base, apaga topo)
                    top = excess_h
                else:
                    # Centralizado (padrão: corta topo e base igualmente)
                    top = excess_h // 2
                
            right = left + crop_w
            bottom = top + crop_h
            
            cropped = img.crop((left, top, right, bottom))
            
            # Redimensionar para a resolução alvo (4K 3840x2160)
            resized = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
            
            # Garantir formato RGB
            if resized.mode != "RGB":
                resized = resized.convert("RGB")
                
            save_kwargs = {"quality": 95}
            if raw_exif:
                save_kwargs["exif"] = raw_exif
                
            resized.save(out_path, "JPEG", **save_kwargs)
            
        return True, out_path, False
    except Exception as e:
        return False, f"Erro em {os.path.basename(img_path)}: {str(e)}", False

def run_step_1_crop(config, max_photos=None):
    """Etapa 1: Cortar e redimensionar fotos em paralelo via PIL preservando metadados EXIF."""
    source_dir = config.get("source_dir", ".")
    output_dir = get_output_dir(config)
    all_photos = find_all_photos(source_dir, config.get("output_dir", "fotos_cortadas_4k"))
    
    if not all_photos:
        print(f"\n[-] Erro: Nenhuma foto JPG/JPEG encontrada na pasta de origem: {os.path.abspath(source_dir)}")
        prompt = input("Deseja informar outra pasta de fotos agora? (s/N): ").strip().lower()
        if prompt == 's':
            select_source_dir(config)
            return run_step_1_crop(config, max_photos=max_photos)
        return False, []

    if max_photos:
        all_photos = all_photos[:max_photos]
        print(f"\n[!] MODO TESTE: Limitando processamento às primeiras {len(all_photos)} fotos.")

    os.makedirs(output_dir, exist_ok=True)
    
    crop_mode = config.get("crop_mode", "bottom")
    crop_label = CROP_MODE_LABELS.get(crop_mode, crop_mode)
    
    total = len(all_photos)
    project_id = logger.get_project_id(source_dir, config.get("output_dir", "fotos_cortadas_4k"))
    tracker.update_stage_status(project_id, "etapa_2", "in_progress")

    print("\n" + "="*66)
    print("        ETAPA 2: CORTE 16:9 E REDIMENSIONAMENTO 4K (PIL)")
    print("="*66)
    print(f"[+] Projeto: {project_id}")
    print(f"[+] Pasta de origem: {os.path.abspath(source_dir)}")
    print(f"[+] Fotos localizadas: {total}")
    print(f"[+] Modo de corte: {crop_label}")
    print(f"[+] Resolução de saída: {config['target_width']}x{config['target_height']} (4K UHD)")
    print(f"[+] Preservação EXIF: Ativada")
    print(f"[+] Núcleos de CPU (Workers): {os.cpu_count()}")
    print(f"[+] Pasta de destino: {output_dir}")
    print("-" * 66)

    tasks = [
        (img_path, output_dir, config["target_width"], config["target_height"], idx + 1, crop_mode)
        for idx, img_path in enumerate(all_photos)
    ]

    start_time = time.time()
    completed = 0
    new_count = 0
    reused_count = 0
    errors = 0

    with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = [executor.submit(process_single_image, t) for t in tasks]
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            success, res, is_reused = future.result()
            if success:
                item_name = os.path.basename(res)
                if is_reused:
                    reused_count += 1
                    item_display = f"{item_name} (Reaproveitado)"
                else:
                    new_count += 1
                    item_display = f"{item_name}"
                    logger.log_event(project_id, "etapa_2_crop", f"Cortado 4K: {item_name}", to_general=False)
            else:
                errors += 1
                item_display = f"Erro: {res}"
                logger.log_event(project_id, "etapa_2_crop", res, level="WARN", to_general=False)
            print_progress_bar(completed, total, start_time, prefix="Processando fotos", current_item=item_display)

    print() # Pular linha
    total_time = time.time() - start_time
    print("-" * 66)
    if errors == 0:
        if reused_count == total:
            print(f"[+] Sucesso! Todas as {total} fotos já estavam cortadas em 4K e foram reaproveitadas em {total_time:.1f}s.")
            details_str = f"Todas as {total} fotos reaproveitadas (já cortadas)"
        else:
            print(f"[+] Sucesso! {total} fotos prontas ({new_count} novas processadas, {reused_count} reaproveitadas) em {total_time:.1f}s.")
            details_str = f"{new_count} fotos cortadas, {reused_count} reaproveitadas em {total_time:.1f}s"
            
        tracker.update_stage_status(project_id, "etapa_2", "completed", details=details_str)
        logger.log_event(project_id, "etapa_2_crop", f"{total} fotos prontas 4K ({new_count} novas, {reused_count} reaproveitadas) em {total_time:.1f}s.")
        ntfy_topic = config.get("ntfy_topic", "timelapse-studio-2026")
        notifier.notify_stage_completion(project_id, 2, "Corte e Redimensionamento 4K", details=details_str, ntfy_topic=ntfy_topic)
    else:
        print(f"[!] Concluído com {errors} erros de {completed} fotos processadas.")
        tracker.update_stage_status(project_id, "etapa_2", "failed", details=f"{errors} erros de {completed} fotos processadas")
        
    print(f"[+] Fotos salvas em: {output_dir}")
    print("=" * 66)
    return errors == 0, output_dir

def detect_ffmpeg_encoder(preset, crf, force_cpu=False):
    """Detecta se há suporte a GPU (NVIDIA NVENC, AMD AMF, Intel QSV) ou faz fallback para CPU libx264."""
    if force_cpu:
        cpu_args = ["-c:v", "libx264", "-profile:v", "high", "-preset", preset, "-crf", str(crf)]
        return "libx264 (CPU)", cpu_args

    encoders_to_test = [
        ("h264_nvenc", ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", str(crf), "-rc", "vbr"]),
        ("h264_amf", ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cbr"]),
        ("h264_qsv", ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", str(crf)])
    ]
    
    for name, args in encoders_to_test:
        test_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=256x256:d=1",
            *args, "-f", "null", "-"
        ]
        try:
            res = subprocess.run(test_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0:
                return name, args
        except Exception:
            pass
            
    # Fallback para CPU libx264
    cpu_args = ["-c:v", "libx264", "-profile:v", "high", "-preset", preset, "-crf", str(crf)]
    return "libx264 (CPU)", cpu_args

def generate_video_info(cropped_photos, is_test=False):
    """
    Calcula o nome dinâmico do vídeo e os metadados de captura com base na primeira e na última foto.
    Formato: timelapse_YYYY-MM-DD_HH-MM---HH-MM.mp4
    """
    if not cropped_photos:
        default_name = "timelapse_teste_4k.mp4" if is_test else "timelapse_4k_cortado.mp4"
        return default_name, datetime.datetime.now(), datetime.datetime.now(), ""
        
    first_dt = get_exif_datetime(cropped_photos[0])
    last_dt = get_exif_datetime(cropped_photos[-1])
    
    first_date_str = first_dt.strftime('%Y-%m-%d')
    last_date_str = last_dt.strftime('%Y-%m-%d')
    first_time_str = first_dt.strftime('%H-%M')
    last_time_str = last_dt.strftime('%H-%M')
    
    if first_date_str == last_date_str:
        range_str = f"{first_date_str}_{first_time_str}---{last_time_str}"
    else:
        range_str = f"{first_date_str}_{first_time_str}---{last_date_str}_{last_time_str}"
        
    prefix = "timelapse_teste" if is_test else "timelapse"
    video_filename = f"{prefix}_{range_str}.mp4"
    
    return video_filename, first_dt, last_dt, range_str

def render_video_ffmpeg(config, cropped_photos, output_path, force_cpu=False, first_dt=None, last_dt=None, range_str=""):
    """Executa a renderização do FFmpeg via pipe com cálculo seguro de GOP, B-frames e injeção de metadados."""
    total_photos = len(cropped_photos)
    fps = config["fps"]
    frames_per_image = max(1, config.get("frames_per_image", 1))
    total_video_frames = total_photos * frames_per_image
    duration_sec = total_video_frames / fps if fps > 0 else 0
    sec_per_photo = frames_per_image / fps if fps > 0 else 0
    
    if first_dt is None and cropped_photos:
        first_dt = get_exif_datetime(cropped_photos[0])
    if last_dt is None and cropped_photos:
        last_dt = get_exif_datetime(cropped_photos[-1])
        
    # Cálculo seguro da estrutura GOP e B-frames conforme o FPS
    if fps <= 2:
        gop_size = max(1, fps)
        b_frames = 0
    else:
        gop_size = max(1, fps // 2)
        b_frames = 2 if gop_size >= 4 else 0

    encoder_name, encoder_args = detect_ffmpeg_encoder(config["preset"], config["crf"], force_cpu=force_cpu)

    start_iso = first_dt.strftime('%Y-%m-%dT%H:%M:%S') if first_dt else datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    start_readable = first_dt.strftime('%Y-%m-%d %H:%M:%S') if first_dt else "Desconhecido"
    end_readable = last_dt.strftime('%Y-%m-%d %H:%M:%S') if last_dt else "Desconhecido"
    title_str = f"Timelapse {range_str}" if range_str else "Timelapse 4K UHD"

    metadata_args = [
        "-metadata", f"creation_time={start_iso}",
        "-metadata", f"date={start_readable}",
        "-metadata", f"title={title_str}",
        "-metadata", f"comment=Início das capturas: {start_readable} | Fim: {end_readable}",
        "-metadata", "description=Timelapse 4K UHD gerado pelo Timelapse Studio"
    ]

    input_dir = get_output_dir(config)

    print("\n" + "="*66)
    print("        ETAPA 2: GERACAO DO VIDEO TIMELAPSE 4K (FFMPEG)")
    print("="*66)
    print(f"[+] Pasta de origem das fotos: {input_dir}")
    print(f"[+] Total de fotos cortadas: {total_photos}")
    print(f"[+] Início das capturas: {start_readable}")
    print(f"[+] Término das capturas: {end_readable}")
    print(f"[+] Encoder selecionado: {encoder_name}")
    print(f"[+] Configuração: {fps} FPS | {frames_per_image} frame(s)/foto ({sec_per_photo:.2f}s/foto)")
    print(f"[+] Duração estimada: {duration_sec:.1f}s ({total_video_frames} quadros)")
    print(f"[+] GOP: {gop_size} | B-Frames: {b_frames} | CRF: {config['crf']}")
    print(f"[+] Arquivo de saída: {os.path.basename(output_path)}")
    print(f"[+] Pasta de destino: {os.path.dirname(output_path)}")
    print("-" * 66)
    print("[>] Enviando imagens para o FFmpeg via pipe...")

    ffmpeg_cmd = [
        "ffmpeg",
        "-loglevel", "error",
        "-y",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "-framerate", f"{fps}/{frames_per_image}",
        "-i", "-",
        "-vf", "format=yuv420p",
        "-r", str(fps),
        *encoder_args,
        *metadata_args,
        "-bf", str(b_frames),
        "-g", str(gop_size),
        "-movflags", "+faststart",
        "-colorspace", "bt709",
        "-color_trc", "bt709",
        "-color_primaries", "bt709",
        output_path
    ]

    start_time = time.time()
    try:
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=None,
            stderr=None
        )
    except FileNotFoundError:
        print("[-] Erro: O executável do FFmpeg não foi encontrado no PATH do sistema.")
        return False, encoder_name

    try:
        for idx, img_path in enumerate(cropped_photos):
            with open(img_path, "rb") as f:
                img_bytes = f.read()
            process.stdin.write(img_bytes)
            print_progress_bar(idx + 1, total_photos, start_time, prefix="Renderizando vídeo", current_item=os.path.basename(img_path))
    except IOError as e:
        print(f"\n[-] Erro de comunicação com o FFmpeg: {e}")
        return False, encoder_name
    finally:
        if process.stdin:
            process.stdin.close()

    ret_code = process.wait()
    total_time = time.time() - start_time
    print() # Pular linha
    print("-" * 66)
    
    if ret_code == 0 and os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"[+] Sucesso! Vídeo timelapse criado com sucesso.")
        print(f"[+] Tempo de renderização: {total_time:.1f} segundos.")
        print(f"[+] Tamanho do arquivo: {size_mb:.2f} MB")
        print(f"[+] Arquivo salvo em: {os.path.abspath(output_path)}")
        print("=" * 66)
        return True, encoder_name
    else:
        print(f"[-] O encoder {encoder_name} encerrou com erro (Código: {ret_code}).")
        return False, encoder_name

def run_step_2_video(config, is_test=False):
    """Etapa 3: Gerar o vídeo timelapse 4K com suporte a fallback automático para CPU e metadados."""
    input_dir = get_output_dir(config)
    source_dir = config.get("source_dir", ".")
    project_id = logger.get_project_id(source_dir, config.get("output_dir", "fotos_cortadas_4k"))
    
    if not os.path.exists(input_dir):
        print(f"\n[-] Erro: A pasta '{input_dir}' não foi encontrada.")
        print("    Por favor, execute a Etapa 2 primeiro para gerar as fotos cortadas.")
        logger.log_event(project_id, "etapa_3_video", f"Pasta de cortes não encontrada: {input_dir}", level="ERROR")
        return False, None

    pattern = os.path.join(input_dir, "*.jpg")
    cropped_photos = sorted(glob.glob(pattern))

    if not cropped_photos:
        print(f"\n[-] Erro: Nenhuma imagem JPG encontrada na pasta '{input_dir}'.")
        logger.log_event(project_id, "etapa_3_video", f"Nenhuma imagem encontrada em: {input_dir}", level="ERROR")
        return False, None

    video_name, first_dt, last_dt, range_str = generate_video_info(cropped_photos, is_test=is_test)
    output_path = os.path.abspath(os.path.join(source_dir, video_name))

    # Evitar retrabalho: se o vídeo já existe com tamanho válido e já foi concluído
    if os.path.exists(output_path) and os.path.getsize(output_path) > 1024 * 1024:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        if tracker.is_stage_completed(project_id, "etapa_3"):
            print("\n" + "=" * 66)
            print("        ETAPA 3: GERAR VÍDEO TIMELAPSE 4K (FFMPEG)")
            print("=" * 66)
            print(f"[i] O vídeo '{video_name}' ({size_mb:.2f} MB) já existe no destino.")
            print("[+] Reaproveitando vídeo já renderizado (sem retrabalho).")
            print(f"[+] Arquivo: {output_path}")
            print("=" * 66)
            return True, output_path

    tracker.update_stage_status(project_id, "etapa_3", "in_progress")
    # Primeira tentativa (utiliza GPU se disponível)
    success, encoder_used = render_video_ffmpeg(
        config, cropped_photos, output_path, force_cpu=False,
        first_dt=first_dt, last_dt=last_dt, range_str=range_str
    )
    
    # Se a GPU (ex: Intel QSV) falhar, faz fallback automático transparente para CPU (libx264)
    if not success and "CPU" not in encoder_used:
        print("\n[!] TENTANDO RENDERIZAR VIA CPU (libx264) COMO FALLBACK DE SEGURANÇA...")
        logger.log_event(project_id, "etapa_3_video", f"Tentando fallback para CPU (GPU {encoder_used} falhou).", level="WARN")
        success, encoder_used = render_video_ffmpeg(
            config, cropped_photos, output_path, force_cpu=True,
            first_dt=first_dt, last_dt=last_dt, range_str=range_str
        )
        
    if success:
        tracker.update_stage_status(project_id, "etapa_3", "completed", details=f"Vídeo: {os.path.basename(output_path)} ({encoder_used})", extra_data={"video_path": output_path})
        logger.log_event(project_id, "etapa_3_video", f"Vídeo renderizado com sucesso: {output_path} ({encoder_used})")
        ntfy_topic = config.get("ntfy_topic", "timelapse-studio-2026")
        notifier.notify_stage_completion(project_id, 3, "Renderização de Vídeo 4K", details=f"Arquivo: {os.path.basename(output_path)} ({encoder_used})", ntfy_topic=ntfy_topic)
        return True, output_path
    else:
        tracker.update_stage_status(project_id, "etapa_3", "failed", details=f"Falha na renderização de {output_path}")
        logger.log_event(project_id, "etapa_3_video", f"Falha na renderização de: {output_path}", level="ERROR")
        return False, None

def quick_change_crop(config):
    """Menu de atalho rápido para alterar a posição de enquadramento/corte (crop 16:9)."""
    current_mode = config.get("crop_mode", "bottom")
    print("\n" + "="*66)
    print("             AJUSTE DE ENQUADRAMENTO / CORTE (CROP 16:9)")
    print("="*66)
    print(f"Modo atual: {CROP_MODE_LABELS.get(current_mode, current_mode)}")
    print("\nEscolha a posição do enquadramento vertical:")
    print("  [1] Por Baixo (Preserva a base, apaga o topo - Foco no chão/pessoas - Padrão)")
    print("  [2] Centro    (Corta igualmente o topo e a base)")
    print("  [3] Por Cima  (Preserva o topo, apaga a base - Foco no céu/paisagem)")
    print("  [0] Cancelar / Manter modo atual")
    print("-" * 66)
    
    choice = input("Escolha uma opção [0-3]: ").strip()
    if choice == "1":
        config["crop_mode"] = "bottom"
        print(f"[+] Modo de corte alterado para: {CROP_MODE_LABELS['bottom']}")
    elif choice == "2":
        config["crop_mode"] = "center"
        print(f"[+] Modo de corte alterado para: {CROP_MODE_LABELS['center']}")
    elif choice == "3":
        config["crop_mode"] = "top"
        print(f"[+] Modo de corte alterado para: {CROP_MODE_LABELS['top']}")
    elif choice == "0":
        print("[+] Modo de corte mantido.")
    else:
        print("[-] Opção inválida. Modo mantido.")

def quick_change_fps(config):
    """Menu de atalho rápido para alterar o FPS do timelapse."""
    print("\n" + "="*66)
    print("             AJUSTE RÁPIDO DE TAXA DE QUADROS (FPS)")
    print("="*66)
    print(f"FPS atual configurado: {config['fps']} fps")
    print("\nEscolha uma opção de FPS predefinida:")
    print("  [1] 15 fps  (Timelapse lento / ideal para poucos quadros)")
    print("  [2] 24 fps  (Velocidade de cinema)")
    print("  [3] 30 fps  (Padrão TV / Youtube clássico)")
    print("  [4] 60 fps  (Máxima fluidez - Padrão)")
    print("  [5] Digitar um valor personalizado de FPS...")
    print("  [0] Cancelar / Manter FPS atual")
    print("-" * 66)
    
    choice = input("Escolha uma opção [0-5]: ").strip()
    if choice == "1":
        config["fps"] = 15
        print(f"[+] FPS alterado para {config['fps']} fps.")
    elif choice == "2":
        config["fps"] = 24
        print(f"[+] FPS alterado para {config['fps']} fps.")
    elif choice == "3":
        config["fps"] = 30
        print(f"[+] FPS alterado para {config['fps']} fps.")
    elif choice == "4":
        config["fps"] = 60
        print(f"[+] FPS alterado para {config['fps']} fps.")
    elif choice == "5":
        val = input("Digite o valor desejado de FPS (ex: 1, 5, 12, 50, 120): ").strip()
        if val.isdigit() and int(val) > 0:
            config["fps"] = int(val)
            print(f"[+] FPS alterado para {config['fps']} fps.")
        else:
            print("[-] Valor de FPS inválido. O FPS atual foi mantido.")
    elif choice == "0":
        print("[+] Manter FPS atual.")

def quick_change_fpi(config):
    """Menu de atalho rápido para alterar a quantidade de frames exibidos por cada imagem/foto."""
    fps = config.get("fps", 60)
    current_fpi = config.get("frames_per_image", 1)
    current_sec = current_fpi / fps if fps > 0 else 0
    print("\n" + "="*66)
    print("        AJUSTE RÁPIDO DE FRAMES POR IMAGEM / FOTO (FPI)")
    print("="*66)
    print(f"Taxa de Quadros (FPS de Saída) : {fps} fps")
    print(f"Frames por Imagem Atual (FPI)  : {current_fpi} frame(s)/foto ({current_sec:.2f}s por foto)")
    print("\nEscolha uma opção predefinida:")
    print(f"  [1] 1 frame por foto    (Padrão - {1/fps:.2f}s por foto / velocidade máxima)")
    print(f"  [2] 2 frames por foto   ({2/fps:.2f}s por foto / 2x mais lento)")
    print(f"  [3] {max(1, fps//2)} frames por foto   ({max(1, fps//2)/fps:.2f}s por foto / meia velocidade)")
    print(f"  [4] {fps} frames por foto   (1.00s por foto / 1 foto por segundo)")
    print(f"  [5] {fps*2} frames por foto  (2.00s por foto / 2 segundos por foto)")
    print("  [6] Digitar um valor personalizado de frames por imagem...")
    print("  [0] Cancelar / Manter valor atual")
    print("-" * 66)
    
    choice = input("Escolha uma opção [0-6]: ").strip()
    if choice == "1":
        config["frames_per_image"] = 1
        print(f"[+] Frames por imagem alterado para 1 frame ({1/fps:.2f}s por foto).")
    elif choice == "2":
        config["frames_per_image"] = 2
        print(f"[+] Frames por imagem alterado para 2 frames ({2/fps:.2f}s por foto).")
    elif choice == "3":
        config["frames_per_image"] = max(1, fps // 2)
        print(f"[+] Frames por imagem alterado para {config['frames_per_image']} frames ({config['frames_per_image']/fps:.2f}s por foto).")
    elif choice == "4":
        config["frames_per_image"] = fps
        print(f"[+] Frames por imagem alterado para {config['frames_per_image']} frames (1.00s por foto).")
    elif choice == "5":
        config["frames_per_image"] = fps * 2
        print(f"[+] Frames por imagem alterado para {config['frames_per_image']} frames (2.00s por foto).")
    elif choice == "6":
        val = input("Digite a quantidade de frames por imagem (ex: 1, 2, 15, 30, 60, 120): ").strip()
        if val.isdigit() and int(val) > 0:
            config["frames_per_image"] = int(val)
            print(f"[+] Frames por imagem alterado para {config['frames_per_image']} frames ({config['frames_per_image']/fps:.2f}s por foto).")
        else:
            print("[-] Valor inválido. O valor atual foi mantido.")
    elif choice == "0":
        print("[+] Frames por imagem mantido.")

def run_test_mode(config):
    """Executa as Etapas 2 e 3 em modo de teste rápido com amostragem reduzida."""
    source_dir = config.get("source_dir", ".")
    project_id = logger.get_project_id(source_dir, config.get("output_dir", "fotos_cortadas_4k"))
    crop_short = {"center": "Centro", "bottom": "Por Baixo", "top": "Por Cima"}.get(config.get("crop_mode", "bottom"), "Por Baixo")
    fps = config.get("fps", 60)
    fpi = config.get("frames_per_image", 1)
    dur_photo = fpi / fps if fps > 0 else 0
    print(f"\n[!] INICIANDO MODO TESTE RÁPIDO ({config['test_sample_size']} FOTOS)")
    print(f"    Projeto: {project_id}")
    print(f"    FPS: {fps} fps | Frames/Foto: {fpi} ({dur_photo:.2f}s/foto) | Corte: {crop_short}")
    
    change_prompt = input("Deseja alterar FPS/Frames por Foto, Pasta de Origem ou Modo de Corte antes do teste? (s/N): ").strip().lower()
    if change_prompt == 's':
        select_source_dir(config)
        quick_change_fps(config)
        quick_change_fpi(config)
        quick_change_crop(config)
        
    logger.log_event(project_id, "resumo_projeto", f"Iniciando Modo Teste ({config['test_sample_size']} fotos)")
    success, _ = run_step_1_crop(config, max_photos=config["test_sample_size"])
    if success:
        run_step_2_video(config, is_test=True)

def run_step_4_clean_crops(config, non_interactive=False, project_id=None):
    """
    Etapa 4: Remove as fotos cortadas intermediárias (fotos_cortadas_4k)
    para liberar espaço em disco após a renderização do vídeo.
    """
    source_dir = config.get("source_dir", ".")
    if not project_id:
        project_id = logger.get_project_id(source_dir, config.get("output_dir", "fotos_cortadas_4k"))
        
    output_dir = get_output_dir(config)
    if not os.path.exists(output_dir):
        if not non_interactive:
            print("\n[!] A pasta de fotos cortadas já não existe ou já foi limpa.")
        tracker.update_stage_status(project_id, "etapa_4", "completed", details="Pasta de cortes já inexistente ou limpa")
        return True
        
    photos = glob.glob(os.path.join(output_dir, "*.jpg"))
    total_files = len(photos)
    size_mb = sum(os.path.getsize(f) for f in photos) / (1024 * 1024) if photos else 0
    
    print("\n" + "=" * 66)
    print("      ETAPA 4: LIMPEZA DE FOTOS CORTADAS INTERMEDIÁRIAS")
    print("=" * 66)
    print(f"[+] Projeto: {project_id}")
    print(f"[+] Pasta de fotos cortadas: {output_dir}")
    print(f"[+] Total de arquivos temporários: {total_files} ({size_mb:.2f} MB)")
    print("-" * 66)
    
    if not non_interactive:
        confirm = input(f"Tem certeza que deseja apagar a pasta '{output_dir}'? (s/N): ").strip().lower()
        if confirm != 's':
            print("[+] Limpeza cancelada pelo usuário. Arquivos mantidos.")
            return False
            
    tracker.update_stage_status(project_id, "etapa_4", "in_progress")
    try:
        import shutil
        start_time = time.time()
        for idx, f in enumerate(photos, 1):
            try:
                os.remove(f)
            except Exception:
                pass
            if idx % 10 == 0 or idx == total_files:
                print_progress_bar(idx, total_files, start_time, prefix="Apagando fotos", current_item=os.path.basename(f))
        try:
            shutil.rmtree(output_dir, ignore_errors=True)
        except Exception:
            pass
            
        print() # Pular linha
        print(f"[+] Sucesso! Pasta temporária '{output_dir}' apagada ({total_files} arquivos, {size_mb:.2f} MB liberados).")
        print("=" * 66)
        tracker.update_stage_status(project_id, "etapa_4", "completed", details=f"{total_files} arquivos temporários apagados ({size_mb:.2f} MB liberados)")
        logger.log_event(project_id, "etapa_4_clean", f"Pasta '{output_dir}' apagada com sucesso ({total_files} arquivos, {size_mb:.2f} MB liberados).")
        ntfy_topic = config.get("ntfy_topic", "timelapse-studio-2026")
        notifier.notify_stage_completion(project_id, 4, "Limpeza de Fotos Intermediárias", details=f"{total_files} fotos apagadas ({size_mb:.2f} MB liberados)", ntfy_topic=ntfy_topic)
        return True
    except Exception as e:
        print(f"[-] Erro ao remover a pasta '{output_dir}': {e}")
        tracker.update_stage_status(project_id, "etapa_4", "failed", details=f"Erro ao remover: {e}")
        logger.log_event(project_id, "etapa_4_clean", f"Erro ao remover '{output_dir}': {e}", level="ERROR")
        return False

def build_youtube_metadata(video_path, config, project_id=None):
    """
    Compila os metadados ricos para o YouTube (Título Opção B, Descrição Detalhada, Tags Dinâmicas).
    Retorna um dicionário com: title, description, tags, privacy_status, category_id.
    """
    source_dir = config.get("source_dir", ".")
    if not project_id:
        project_id = logger.get_project_id(source_dir, config.get("output_dir", "fotos_cortadas_4k"))
        
    fps = config.get("fps", 60)
    fpi = max(1, config.get("frames_per_image", 1))
    target_w = config.get("target_width", 3840)
    target_h = config.get("target_height", 2160)
    crf = config.get("crf", 15)
    preset = config.get("preset", "ultrafast")
    crop_mode = config.get("crop_mode", "center")
    crop_label = CROP_MODE_LABELS.get(crop_mode, crop_mode.capitalize())
    privacy = config.get("youtube_privacy_status", "unlisted")
    category = config.get("youtube_category_id", "22")
    
    # 1. Obter fotos da pasta de origem para extrair dados ricos
    photos = find_all_photos(source_dir, config.get("output_dir", "fotos_cortadas_4k"))
    
    # Se a pasta de origem configurada não tem fotos, mas temos o vídeo, buscar fotos na pasta do próprio vídeo
    if not photos and video_path and os.path.exists(video_path):
        video_dir = os.path.dirname(os.path.abspath(video_path))
        if os.path.isdir(video_dir):
            candidate_photos = find_all_photos(video_dir, config.get("output_dir", "fotos_cortadas_4k"))
            if candidate_photos:
                photos = candidate_photos

    first_dt = None
    last_dt = None
    total_photos = len(photos) if photos else 0
    cam_info = {"camera": None, "original_width": None, "original_height": None}
    gps_info = None
    geo_info = None
    
    if photos:
        first_dt = get_exif_datetime(photos[0])
        last_dt = get_exif_datetime(photos[-1])
        cam_info = get_photo_camera_info(photos[0])
        # Tenta obter GPS da primeira foto ou das primeiras 5 fotos (caso o lock tenha levado alguns segundos)
        for p in photos[:5]:
            gps_info = get_photo_gps_coordinates(p)
            if gps_info:
                break

    # Se as fotos não tinham datas ou não havia fotos, tenta extrair datas do nome do vídeo
    if (not first_dt or not last_dt) and video_path:
        v_first, v_last = parse_datetime_from_video_filename(video_path)
        if not first_dt:
            first_dt = v_first
        if not last_dt:
            last_dt = v_last

    # Obter geocoding reverso se coordenadas GPS foram encontradas
    location_payload = None
    if gps_info:
        geo_info = reverse_geocode_coordinates(gps_info["latitude"], gps_info["longitude"])
        loc_desc = geo_info.get("formatted_address") or f"{gps_info['latitude']:.4f}, {gps_info['longitude']:.4f}"
        location_payload = {
            "latitude": gps_info["latitude"],
            "longitude": gps_info["longitude"],
            "altitude": gps_info.get("altitude"),
            "location_description": loc_desc
        }

    # 2. Montar Título (Padrão Opção B: YYYY-MM-DD (HH:MM - HH:MM) - Timelapse 4K UHD)
    if first_dt and last_dt:
        d1_str = first_dt.strftime('%Y-%m-%d')
        d2_str = last_dt.strftime('%Y-%m-%d')
        t1_str = first_dt.strftime('%H:%M')
        t2_str = last_dt.strftime('%H:%M')
        
        if d1_str == d2_str:
            title = f"{d1_str} ({t1_str} - {t2_str}) - Timelapse 4K UHD"
        else:
            title = f"{d1_str} a {d2_str} ({t1_str} - {t2_str}) - Timelapse 4K UHD"
    elif first_dt:
        d1_str = first_dt.strftime('%Y-%m-%d')
        t1_str = first_dt.strftime('%H:%M')
        title = f"{d1_str} ({t1_str}) - Timelapse 4K UHD"
    else:
        now_dt = datetime.datetime.now()
        title = f"{now_dt.strftime('%Y-%m-%d')} - Timelapse 4K UHD"
        
    title = title[:100]

    # 3. Métricas de Duração e Compressão
    real_dur_str = "Não disponível"
    video_dur_str = "Não disponível"
    speedup_str = None
    interval_str = None
    
    if first_dt and last_dt:
        real_sec = max(0, int((last_dt - first_dt).total_seconds()))
        rh = real_sec // 3600
        rm = (real_sec % 3600) // 60
        rs = real_sec % 60
        if rh > 0:
            real_dur_str = f"{rh}h {rm:02d}m" if rm > 0 else f"{rh}h"
        elif rm > 0:
            real_dur_str = f"{rm}m {rs:02d}s"
        else:
            real_dur_str = f"{rs}s"
            
        if total_photos > 0:
            total_frames = total_photos * fpi
            vid_sec = total_frames / fps if fps > 0 else 0
            vm = int(vid_sec // 60)
            vs = int(vid_sec % 60)
            video_dur_str = f"{vm}:{vs:02d} min ({vid_sec:.1f}s)" if vm > 0 else f"{vid_sec:.1f}s"
            
            if vid_sec > 0 and real_sec > 0:
                speedup = real_sec / vid_sec
                speedup_str = f"comprimido ~{speedup:.0f}x mais rápido que o tempo real"
                
            if total_photos > 1 and real_sec > 0:
                avg_interval = real_sec / (total_photos - 1)
                interval_str = f"1 foto a cada ~{avg_interval:.1f}s"

    # 4. Montar Descrição Rica
    now_str = datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    lines = [
        f"Vídeo timelapse gravado e renderizado em resolução 4K Ultra HD ({target_w}x{target_h}) a {fps} FPS.",
        "",
        "📅 DETALHES DA CAPTURA"
    ]
    
    if first_dt and last_dt:
        d_rec = first_dt.strftime('%d/%m/%Y')
        if first_dt.date() != last_dt.date():
            d_rec += f" a {last_dt.strftime('%d/%m/%Y')}"
        lines.append(f"• Data da Gravação: {d_rec}")
        lines.append(f"• Horário: {first_dt.strftime('%H:%M:%S')} às {last_dt.strftime('%H:%M:%S')} (Início ao Fim)")
        lines.append(f"• Duração no Mundo Real: {real_dur_str}")
    elif first_dt:
        lines.append(f"• Data da Gravação: {first_dt.strftime('%d/%m/%Y')}")
        lines.append(f"• Horário de Início: {first_dt.strftime('%H:%M:%S')}")
        
    if total_photos > 0:
        dur_line = f"• Duração do Vídeo: {video_dur_str}"
        if speedup_str:
            dur_line += f" ({speedup_str})"
        lines.append(dur_line)
        if interval_str:
            lines.append(f"• Intervalo Médio: {interval_str}")
        lines.append(f"• Total de Fotos: {total_photos:,}".replace(",", "."))

    # Seção Localização & GPS
    if gps_info:
        lines.append("")
        lines.append("📍 LOCALIZAÇÃO & GEOLOCALIZAÇÃO")
        if geo_info and geo_info.get("formatted_address"):
            lines.append(f"• Local: {geo_info['formatted_address']}")
        alt_str = f" (Altitude: {gps_info['altitude']:.1f}m)" if gps_info.get("altitude") is not None else ""
        lines.append(f"• Coordenadas GPS: {gps_info['latitude']:.6f}, {gps_info['longitude']:.6f}{alt_str}")
        lines.append(f"• Google Maps: https://www.google.com/maps?q={gps_info['latitude']:.6f},{gps_info['longitude']:.6f}")
        
    # Seção Equipamento
    lines.append("")
    lines.append("📷 EQUIPAMENTO & EXIF")
    if cam_info.get("camera"):
        lines.append(f"• Câmera: {cam_info['camera']}")
    else:
        lines.append("• Câmera: Câmera Digital / Action Cam")
        
    if cam_info.get("original_width") and cam_info.get("original_height"):
        lines.append(f"• Resolução Original: {cam_info['original_width']}x{cam_info['original_height']} ➔ {target_w}x{target_h} (16:9)")
    else:
        lines.append(f"• Enquadramento Alvo: {target_w}x{target_h} (Proporção 16:9)")

    # Seção Especificações Técnicas
    lines.append("")
    lines.append("⚙️ ESPECIFICAÇÕES TÉCNICAS")
    lines.append(f"• Resolução Final: {target_w}x{target_h} (4K UHD - 2160p)")
    lines.append(f"• Taxa de Quadros: {fps} FPS ({fpi} frame(s) por foto)")
    lines.append(f"• Enquadramento: Recorte {crop_label} 16:9 (LANCZOS)")
    lines.append(f"• Qualidade / CRF: CRF {crf} (Máxima fidelidade visual)")
    lines.append(f"• Preset FFmpeg: {preset}")
    lines.append("• Espaço de Cor: BT.709 / YUV420p (Padrão Oficial 4K)")
    lines.append("• Software: Timelapse Studio 4K UHD (PIL Multiprocessing + FFmpeg)")

    # Seção Projeto
    lines.append("")
    lines.append("🆔 PROJETO & SISTEMA")
    lines.append(f"• ID do Projeto: {project_id}")
    lines.append(f"• Renderizado em: {now_str}")
    lines.append("")
    lines.append("──────────────────────────────────────")
    lines.append("#Timelapse #4KUHD #4KTimelapse #UltraHD #Photography #TimeLapseStudio #60FPS")
    
    description = "\n".join(lines)[:5000]

    # 5. Tags Inteligentes
    tags = ["timelapse", "timelapse 4k", "4k uhd", "60fps timelapse", "ultra hd", "timelapse studio", "photography", "hyperlapse", "4k"]
    if first_dt:
        tags.append(f"timelapse {first_dt.year}")
        tags.append(first_dt.strftime('%Y-%m-%d'))
    if cam_info.get("camera"):
        cam_tag = cam_info["camera"].lower()
        if cam_tag not in tags:
            tags.append(cam_tag)
            
    # Adicionar tags de localização se encontradas
    if geo_info:
        for entity in [geo_info.get("city"), geo_info.get("state"), geo_info.get("country")]:
            if entity:
                ent_clean = str(entity).strip().lower()
                if ent_clean and ent_clean not in tags:
                    tags.append(ent_clean)
                    
    tags.extend([f"{target_w}x{target_h}", "2160p", f"{fps}fps"])
    
    # Custom tags de config
    custom_tags = config.get("youtube_custom_tags", [])
    if isinstance(custom_tags, list):
        for ct in custom_tags:
            ct_clean = str(ct).strip().lower()
            if ct_clean and ct_clean not in tags:
                tags.append(ct_clean)
                
    # Remover duplicatas preservando ordem
    unique_tags = []
    for t in tags:
        if t and t not in unique_tags:
            unique_tags.append(t)

    recording_date_iso = first_dt.strftime('%Y-%m-%dT%H:%M:%S.000Z') if first_dt else None

    return {
        "title": title,
        "description": description,
        "tags": unique_tags,
        "privacy_status": privacy,
        "category_id": str(category),
        "location": location_payload,
        "recording_date": recording_date_iso
    }

def display_youtube_metadata_card(metadata, video_path):
    """Exibe o card visual de pré-visualização dos metadados formatados."""
    file_size_mb = os.path.getsize(video_path) / (1024 * 1024) if os.path.exists(video_path) else 0
    title = metadata.get("title", "")
    desc = metadata.get("description", "")
    tags = metadata.get("tags", [])
    privacy = metadata.get("privacy_status", "unlisted").upper()
    category = metadata.get("category_id", "22")
    loc_data = metadata.get("location")
    
    print("\n" + "=" * 66)
    print("      📺 PRÉ-VISUALIZAÇÃO DE PUBLICAÇÃO NO YOUTUBE (API OFICIAL)")
    print("=" * 66)
    print(f" Arquivo    : {os.path.basename(video_path)} ({file_size_mb:.2f} MB)")
    print(f" Privacidade: {privacy} | Categoria: {category} (People & Blogs)")
    if loc_data:
        loc_desc = loc_data.get("location_description", "")
        lat = loc_data.get("latitude")
        lon = loc_data.get("longitude")
        alt = loc_data.get("altitude")
        alt_str = f" | Alt: {alt:.1f}m" if alt is not None else ""
        print(f" 📍 Local    : {loc_desc} ({lat:.4f}, {lon:.4f}{alt_str})")
    print("-" * 66)
    print(f" 🏷️  TÍTULO ({len(title)}/100 car.):")
    print(f"    {title}")
    print("-" * 66)
    print(" 📝 DESCRIÇÃO:")
    for line in desc.splitlines():
        print(f"    {line}")
    print("-" * 66)
    tags_str = ", ".join(tags)
    if len(tags_str) > 60:
        tags_display = tags_str[:57] + "..."
    else:
        tags_display = tags_str
    print(f" 🏷️  TAGS ({len(tags)} tags): {tags_display}")
    print("=" * 66)

def preview_and_confirm_youtube_metadata(metadata, video_path, interval_seconds=180, non_interactive=False):
    """
    Exibe a tela de pré-visualização de metadados do YouTube com contagem regressiva
    para publicação automática se não for interrompida.
    
    Atalhos:
      [ENTER] / [ESPAÇO] : Enviar imediatamente
      [E]                : Editar metadados (Título, Descrição, Tags, Privacidade, Localização)
      [P]                : Pausar / Retomar contagem
      [C] / [Q] / [ESC]  : Cancelar envio
    """
    if non_interactive or interval_seconds <= 0:
        display_youtube_metadata_card(metadata, video_path)
        print("[+] Prosseguindo com o envio para o YouTube...")
        return True, metadata

    current_meta = dict(metadata)
    
    msvcrt = None
    if sys.platform == "win32":
        try:
            import msvcrt
        except ImportError:
            msvcrt = None

    while True:
        display_youtube_metadata_card(current_meta, video_path)
        print(f" ⏱️  Envio automático em: {interval_seconds}s ({interval_seconds/60:.1f} min) se não houver interação")
        print(" [ENTER/ESPAÇO] Enviar Agora | [E] Editar | [P] Pausar | [C/Q] Cancelar")
        print("-" * 66)
        
        remaining = interval_seconds
        paused = False
        action = None
        
        while remaining > 0 or paused:
            if msvcrt and msvcrt.kbhit():
                ch = msvcrt.getch()
                try:
                    ch_str = ch.decode('utf-8', errors='ignore').lower()
                except Exception:
                    ch_str = ""
                    
                if ch in [b'\r', b'\n', b' ']:
                    sys.stdout.write(f"\r[+] Avançando imediatamente para o upload no YouTube!          \n")
                    sys.stdout.flush()
                    return True, current_meta
                elif ch_str in ['e', 'E']:
                    action = "edit"
                    break
                elif ch_str in ['p', 'P']:
                    paused = not paused
                    if paused:
                        sys.stdout.write(f"\r⏸️  CONTAGEM PAUSADA! Pressione [P] ou [ENTER] para retomar...   ")
                        sys.stdout.flush()
                    else:
                        sys.stdout.write(f"\r▶️  Contagem retomada! Continuando...                             \n")
                        sys.stdout.flush()
                elif ch_str in ['c', 'C', 'q', 'Q', '\x1b']:
                    sys.stdout.write(f"\n[!] Upload no YouTube cancelado pelo usuário.\n")
                    sys.stdout.flush()
                    return False, None

            if not paused:
                mins, secs = divmod(remaining, 60)
                sys.stdout.write(f"\r⏳ Envio automático em {mins:02d}:{secs:02d} | [ENTER] Enviar Já | [E] Editar | [P] Pausa | [C] Cancelar... ")
                sys.stdout.flush()
                time.sleep(1.0)
                remaining -= 1
            else:
                time.sleep(0.5)
                
        if action == "edit":
            print("\n")
            print("=" * 66)
            print("             EDIÇÃO RÁPIDA DE METADADOS DO YOUTUBE")
            print("=" * 66)
            print("  [1] Editar Título")
            print("  [2] Editar Descrição")
            print("  [3] Adicionar / Alterar Tags")
            print("  [4] Alterar Privacidade (unlisted / public / private)")
            print("  [5] Editar / Inserir Nome da Localização")
            print("  [0] Concluir Edições e Retornar ao Preview")
            print("-" * 66)
            sub_choice = input("Escolha o campo para editar [0-5]: ").strip()
            if sub_choice == "1":
                print(f"\nTítulo atual: {current_meta['title']}")
                new_title = input("Novo Título (ou Enter para manter): ").strip()
                if new_title:
                    current_meta["title"] = new_title[:100]
                    print(f"[+] Título atualizado ({len(current_meta['title'])} car.)")
            elif sub_choice == "2":
                print(f"\nDescrição atual:\n{current_meta['description']}\n")
                print("Digite a nova descrição (deixe em branco para manter):")
                new_desc = input("Nova Descrição: ").strip()
                if new_desc:
                    current_meta["description"] = new_desc[:5000]
                    print("[+] Descrição atualizada.")
            elif sub_choice == "3":
                print(f"\nTags atuais: {', '.join(current_meta['tags'])}")
                new_tags_input = input("Digite novas tags separadas por vírgula (ou Enter para manter): ").strip()
                if new_tags_input:
                    new_tags = [t.strip() for t in new_tags_input.split(",") if t.strip()]
                    if new_tags:
                        current_meta["tags"] = new_tags
                        print(f"[+] Tags atualizadas: {len(new_tags)} tags definidas.")
            elif sub_choice == "4":
                print(f"\nPrivacidade atual: {current_meta['privacy_status']}")
                print("  [1] unlisted (Não listado)")
                print("  [2] private  (Privado)")
                print("  [3] public   (Público)")
                p_opt = input("Escolha [1/2/3]: ").strip()
                if p_opt == "1":
                    current_meta["privacy_status"] = "unlisted"
                elif p_opt == "2":
                    current_meta["privacy_status"] = "private"
                elif p_opt == "3":
                    current_meta["privacy_status"] = "public"
                print(f"[+] Privacidade definida para: {current_meta['privacy_status']}")
            elif sub_choice == "5":
                cur_loc = current_meta.get("location") or {}
                cur_desc = cur_loc.get("location_description", "")
                print(f"\nLocalização atual: {cur_desc or 'Nenhuma'}")
                new_loc_desc = input("Novo nome do local / cidade (ou Enter para manter): ").strip()
                if new_loc_desc:
                    if not current_meta.get("location"):
                        current_meta["location"] = {}
                    current_meta["location"]["location_description"] = new_loc_desc
                    print(f"[+] Localização definida para: {new_loc_desc}")
            
            # Após editar, retorna para o loop do preview com o tempo reiniciado
            continue

        # Se o loop de contagem zerou sem intervenção do usuário
        if remaining <= 0 and not paused:
            sys.stdout.write(f"\r[+] Tempo esgotado! Iniciando upload automático para o YouTube...     \n")
            sys.stdout.flush()
            return True, current_meta

def confirm_reupload_with_countdown(seconds=180):
    """
    Solicita confirmação para reenviar um vídeo já publicado anteriormente no YouTube
    com contagem regressiva interativa (padrão: 180 segundos).
    Se o usuário não responder dentro do tempo limite, assume automaticamente 'NÃO' (upload cancelado).
    
    Teclas:
      [S] / [Y]                         : Confirmar reenvio
      [N] / [C] / [Q] / [ENTER] / [ESC] : Cancelar reenvio (ou após 180s esgotados)
    """
    msvcrt = None
    if sys.platform == "win32":
        try:
            import msvcrt
        except ImportError:
            msvcrt = None

    print("⚠️  Deseja reenviar o vídeo para o YouTube novamente?")
    print("    [S] Sim (Reenviar) | [N/ENTER] Não (Cancelar)")
    print(f"    (Tempo limite: {seconds}s | Se não houver resposta a tempo, será considerado NÃO)")
    print("-" * 66)

    remaining = seconds
    start_time = time.time()

    if msvcrt:
        # Limpa qualquer tecla pendente no buffer
        while msvcrt.kbhit():
            msvcrt.getch()

        while remaining > 0:
            mins, secs = divmod(remaining, 60)
            sys.stdout.write(f"\r⏳ Tempo restante: {mins:02d}:{secs:02d} | Escolha [S] Sim ou [N] Não: ")
            sys.stdout.flush()

            for _ in range(10):
                if msvcrt.kbhit():
                    ch = msvcrt.getch()
                    try:
                        ch_str = ch.decode('utf-8', errors='ignore').lower()
                    except Exception:
                        ch_str = ""

                    if ch_str in ['s', 'y']:
                        sys.stdout.write(f"\r[+] Resposta: SIM. Prosseguindo com o reenvio para o YouTube!              \n")
                        sys.stdout.flush()
                        return True
                    elif ch_str in ['n', 'c', 'q'] or ch in [b'\r', b'\n', b'\x1b']:
                        sys.stdout.write(f"\r[-] Resposta: NÃO. Envio cancelado a pedido do usuário.                    \n")
                        sys.stdout.flush()
                        return False

                time.sleep(0.1)

            elapsed = int(time.time() - start_time)
            remaining = max(0, seconds - elapsed)

        sys.stdout.write(f"\r[!] Tempo esgotado ({seconds}s)! Resposta considerada: NÃO (Upload cancelado).      \n")
        sys.stdout.flush()
        return False
    else:
        try:
            import select
            sys.stdout.write(f"Escolha [s/N] (Tempo limite {seconds}s): ")
            sys.stdout.flush()
            rlist, _, _ = select.select([sys.stdin], [], [], seconds)
            if rlist:
                ans = sys.stdin.readline().strip().lower()
                return ans in ["s", "sim", "y", "yes"]
            else:
                print(f"\n[!] Tempo esgotado ({seconds}s)! Resposta considerada: NÃO.")
                return False
        except Exception:
            ans = input(f"Escolha [s/N] (Enter para Não): ").strip().lower()
            return ans in ["s", "sim", "y", "yes"]

def run_step_5_youtube_upload(config, video_path=None, project_id=None, non_interactive=False):
    """
    Etapa 5: Publicação oficial de vídeo no YouTube com metadados ricos, preview interativo e auto-envio.
    """
    source_dir = config.get("source_dir", ".")
    if not project_id:
        project_id = logger.get_project_id(source_dir, config.get("output_dir", "fotos_cortadas_4k"))

    while not video_path:
        video_files = sorted(glob.glob(os.path.join(source_dir, "*.mp4")))
        if not video_files:
            print(f"\n[-] Nenhum vídeo .mp4 encontrado na pasta de origem '{os.path.abspath(source_dir)}'.")
            custom_path = input("Digite ou arraste o arquivo .mp4 ou a pasta com o vídeo (ou Enter para cancelar): ").strip()
            if not custom_path:
                print("[+] Upload cancelado.")
                return False, None
            resolved = resolve_custom_video_path(custom_path)
            if not resolved:
                continue
            video_path = resolved
        elif len(video_files) == 1:
            video_path = os.path.abspath(video_files[0])
            print(f"\n[+] Vídeo selecionado: {os.path.basename(video_path)}")
        else:
            print("\n" + "=" * 66)
            print("           SELEÇÃO DE VÍDEO PARA UPLOAD NO YOUTUBE")
            print("=" * 66)
            for idx, vf in enumerate(video_files, 1):
                sz = os.path.getsize(vf) / (1024 * 1024)
                print(f"  [{idx}] {os.path.basename(vf)} ({sz:.2f} MB)")
            print("  [0] Digitar outro caminho / Cancelar")
            print("-" * 66)
            vchoice = input(f"Escolha o vídeo para upload [1-{len(video_files)}]: ").strip()
            if vchoice.isdigit() and 1 <= int(vchoice) <= len(video_files):
                video_path = os.path.abspath(video_files[int(vchoice) - 1])
            else:
                custom_path = input("Digite ou arraste o arquivo .mp4 ou a pasta com o vídeo (ou Enter para cancelar): ").strip()
                if not custom_path:
                    print("[+] Upload cancelado.")
                    return False, None
                resolved = resolve_custom_video_path(custom_path)
                if not resolved:
                    continue
                video_path = resolved

    # Validação de integridade do arquivo
    if not os.path.isfile(video_path):
        print(f"[-] O caminho selecionado '{video_path}' não é um arquivo regular.")
        return False, None

    # Se a pasta de origem não continha fotos, derivar o project_id com base na pasta do vídeo
    video_dir = os.path.dirname(os.path.abspath(video_path))
    if os.path.isdir(video_dir):
        if not find_all_photos(source_dir, config.get("output_dir", "fotos_cortadas_4k")):
            derived_pid = logger.get_project_id(video_dir, config.get("output_dir", "fotos_cortadas_4k"))
            if derived_pid:
                project_id = derived_pid

    # Evitar retrabalho acidental: se o vídeo deste projeto já foi enviado para o YouTube
    existing_stage5 = tracker.get_stage_info(project_id, "etapa_5")
    if existing_stage5.get("status") == "completed" and existing_stage5.get("youtube_url"):
        existing_url = existing_stage5["youtube_url"]
        print("\n" + "=" * 66)
        print("          ETAPA 5: PUBLICAÇÃO DE VÍDEO NO YOUTUBE")
        print("=" * 66)
        print(f"[i] O vídeo deste projeto já foi publicado anteriormente no YouTube:")
        print(f"    🔗 {existing_url}")
        print("-" * 66)
        if non_interactive:
            print("[+] Modo não-interativo: upload ignorado para evitar duplicação.")
            print("=" * 66)
            return True, existing_url
            
        interval_s = config.get("stage_interval_seconds", 180)
        reupload_confirmed = confirm_reupload_with_countdown(seconds=interval_s)
        if not reupload_confirmed:
            print("=" * 66)
            return True, existing_url
            
        print("=" * 66)

    metadata = build_youtube_metadata(video_path, config, project_id=project_id)
    interval_s = config.get("stage_interval_seconds", 180)
    
    confirmed, final_metadata = preview_and_confirm_youtube_metadata(
        metadata, video_path, interval_seconds=interval_s, non_interactive=non_interactive
    )
    
    if not confirmed or not final_metadata:
        tracker.update_stage_status(project_id, "etapa_5", "skipped", details="Upload cancelado pelo usuário na tela de preview")
        logger.log_event(project_id, "etapa_5_youtube", "Upload cancelado pelo usuário na tela de preview.")
        return False, None
        
    tracker.update_stage_status(project_id, "etapa_5", "in_progress")
    try:
        success, url, vid = youtube_uploader.upload_video_resumable(video_path, metadata=final_metadata, project_id=project_id)
    except Exception as e:
        logger.log_event(project_id, "etapa_5_youtube", f"Exceção durante upload: {e}", level="ERROR")
        print(f"\n[-] Erro inesperado durante o upload: {e}")
        success, url, vid = False, None, None

    ntfy_topic = config.get("ntfy_topic", "timelapse-studio-2026")
    privacy = final_metadata.get("privacy_status", "unlisted")
    
    if success and url:
        tracker.update_stage_status(project_id, "etapa_5", "completed", details=f"Publicado no YouTube: {url}", extra_data={"youtube_url": url, "video_id": vid})
        notifier.notify_stage_completion(project_id, 5, "Publicação no YouTube", details=f"Vídeo publicado com sucesso ({privacy.upper()})", youtube_url=url, ntfy_topic=ntfy_topic)
    else:
        tracker.update_stage_status(project_id, "etapa_5", "failed", details="Falha no upload para o YouTube")
        
    return success, url

def wait_stage_interval(seconds=180, next_stage_name="Próxima Etapa", current_stage_name="Etapa Concluída"):
    """
    Exibe uma contagem regressiva interativa entre etapas (padrão: 180s / 3 minutos)
    com opções de avançar imediatamente ([ENTER]/[ESPAÇO]), pausar ([P]) ou cancelar ([C]/[Q]).
    Retorna True se deve prosseguir ou False se foi cancelado pelo usuário.
    """
    if seconds <= 0:
        return True

    print("\n" + "=" * 66)
    print(f" ⏳ {current_stage_name.upper()} CONCLUÍDA COM SUCESSO!")
    print(f" ⏱️  Intervalo de segurança: {seconds}s (3 min) antes de iniciar {next_stage_name}")
    print(" [ENTER/ESPAÇO] Avançar Imediatamente | [P] Pausar | [C/Q] Cancelar Fluxo")
    print("-" * 66)
    
    msvcrt = None
    if sys.platform == "win32":
        try:
            import msvcrt
        except ImportError:
            msvcrt = None

    remaining = seconds
    paused = False
    
    while remaining > 0 or paused:
        if msvcrt and msvcrt.kbhit():
            ch = msvcrt.getch()
            try:
                ch_str = ch.decode('utf-8', errors='ignore').lower()
            except Exception:
                ch_str = ""
                
            if ch in [b'\r', b'\n', b' ']:
                sys.stdout.write(f"\r[+] Avançando imediatamente para: {next_stage_name}               \n")
                sys.stdout.flush()
                return True
            elif ch_str in ['p', 'P']:
                paused = not paused
                if paused:
                    sys.stdout.write(f"\r⏸️  FLUXO PAUSADO! Pressione [P] ou [ENTER] para retomar...          ")
                    sys.stdout.flush()
                else:
                    sys.stdout.write(f"\r▶️  Fluxo retomado! Continuando contagem...                        \n")
                    sys.stdout.flush()
            elif ch_str in ['c', 'C', 'q', 'Q', '\x1b']:
                sys.stdout.write(f"\n[!] Fluxo cancelado pelo usuário durante o intervalo de segurança.\n")
                sys.stdout.flush()
                return False
                
        if not paused:
            mins, secs = divmod(remaining, 60)
            sys.stdout.write(f"\r⏳ Próxima etapa em: {mins:02d}:{secs:02d} | [ENTER] Avançar | [P] Pausa | [C] Cancelar... ")
            sys.stdout.flush()
            time.sleep(1.0)
            remaining -= 1
        else:
            time.sleep(0.5)

    sys.stdout.write(f"\r[+] Intervalo concluído! Iniciando {next_stage_name}...                       \n")
    sys.stdout.flush()
    return True

def run_full_pipeline(config):
    """
    Executa o fluxo completo de 5 etapas:
    Etapa 1: Organizar/Renomear fotos de origem por EXIF
    Etapa 2: Cortar e redimensionar fotos para 4K UHD 16:9
    Etapa 3: Gerar vídeo timelapse 4K
    Etapa 4: Limpar fotos cortadas intermediárias (se auto_clean_crops estiver ativo)
    Etapa 5: Publicar vídeo no YouTube (se youtube_auto_upload estiver ativo)
    """
    source_dir = config.get("source_dir", ".")
    project_id = logger.get_project_id(source_dir, config.get("output_dir", "fotos_cortadas_4k"))
    
    crop_short = {"center": "Centro", "bottom": "Por Baixo", "top": "Por Cima"}.get(config.get("crop_mode", "bottom"), "Por Baixo")
    fps = config.get("fps", 60)
    fpi = config.get("frames_per_image", 1)
    dur_photo = fpi / fps if fps > 0 else 0
    auto_clean = config.get("auto_clean_crops", False)
    yt_auto = config.get("youtube_auto_upload", True)
    yt_priv = config.get("youtube_privacy_status", "unlisted")
    interval_s = config.get("stage_interval_seconds", 180)
    
    print("\n" + "=" * 66)
    print("      INICIANDO FLUXO COMPLETO (ETAPAS 1 ➔ 2 ➔ 3 ➔ 4 ➔ 5)")
    print("=" * 66)
    print(f"    Projeto     : {project_id}")
    print(f"    Configuração: {fps} FPS | {fpi} frame(s)/foto ({dur_photo:.2f}s/foto) | {config['target_width']}x{config['target_height']} | CRF {config['crf']} | Corte: {crop_short}")
    print(f"    Limpeza pós-vídeo : {'Ativada' if auto_clean else 'Desativada'}")
    print(f"    Upload YouTube    : {'Ativado (' + yt_priv + ')' if yt_auto else 'Desativado'}")
    print(f"    Pausa entre etapas: {interval_s}s (3 min)")
    print("-" * 66)
    
    logger.log_event(project_id, "resumo_projeto", f"Iniciando Fluxo Completo | FPS: {fps} | FPI: {fpi} | CRF: {config['crf']}")
    
    # Etapa 1: Renomear fotos de origem por EXIF
    print("\n>>> [1/5] ETAPA 1: Organizando e Renomeando Fotos de Origem por EXIF...")
    renamed = rename_source_photos(config["source_dir"], config["output_dir"], non_interactive=True, project_id=project_id, config=config)
    
    # Intervalo de segurança após Etapa 1
    if not wait_stage_interval(interval_s, "Etapa 2 (Corte e Redimensionamento 4K)", "Etapa 1 (Renomeação EXIF)"):
        print("\n[!] Fluxo cancelado após a Etapa 1. Status salvo.")
        return
        
    # Etapa 2: Cortar e Redimensionar Fotos para 4K
    print("\n>>> [2/5] ETAPA 2: Cortando e Redimensionando Fotos para 4K UHD...")
    crop_ok, _ = run_step_1_crop(config)
    if not crop_ok:
        msg = "Interrompendo pipeline: falha na Etapa 2 (Corte)."
        print(f"\n[-] {msg}")
        logger.log_event(project_id, "resumo_projeto", msg, level="ERROR")
        return
        
    # Intervalo de segurança após Etapa 2
    if not wait_stage_interval(interval_s, "Etapa 3 (Renderização de Vídeo 4K)", "Etapa 2 (Corte 4K)"):
        print("\n[!] Fluxo cancelado após a Etapa 2. Status salvo.")
        return
        
    # Etapa 3: Renderizar Vídeo Timelapse 4K
    print("\n>>> [3/5] ETAPA 3: Renderizando Vídeo Timelapse 4K...")
    video_ok, video_path = run_step_2_video(config, is_test=False)
    if not video_ok or not video_path:
        msg = "Interrompendo pipeline: falha na Etapa 3 (Renderização de Vídeo)."
        print(f"\n[-] {msg}")
        logger.log_event(project_id, "resumo_projeto", msg, level="ERROR")
        return
        
    # Etapa 4: Limpeza das fotos cortadas intermediárias
    if auto_clean:
        if not wait_stage_interval(interval_s, "Etapa 4 (Limpeza de Fotos Temporárias)", "Etapa 3 (Renderização de Vídeo)"):
            print("\n[!] Fluxo cancelado após a Etapa 3. Vídeo gerado foi mantido.")
            return
        print("\n>>> [4/5] ETAPA 4: Limpando Fotos Cortadas Intermediárias...")
        run_step_4_clean_crops(config, non_interactive=True, project_id=project_id)
    else:
        print("\n[i] Etapa 4 ignorada (auto_clean_crops desativado nas configurações).")
        
    # Etapa 5: Publicação no YouTube
    yt_url = None
    if yt_auto:
        next_etapa_label = "Etapa 5 (Publicação no YouTube)"
        prev_etapa_label = "Etapa 4 (Limpeza)" if auto_clean else "Etapa 3 (Renderização de Vídeo)"
        if not wait_stage_interval(interval_s, next_etapa_label, prev_etapa_label):
            print("\n[!] Fluxo cancelado antes do upload. O vídeo local foi mantido.")
            return
            
        print("\n>>> [5/5] ETAPA 5: Publicando Vídeo no YouTube...")
        yt_ok, yt_url = run_step_5_youtube_upload(config, video_path=video_path, project_id=project_id)
        if not yt_ok:
            print("\n[!] Aviso: Não foi possível concluir o upload no YouTube, mas o vídeo local foi gerado com sucesso.")
    else:
        print("\n[i] Etapa 5 ignorada (youtube_auto_upload desativado nas configurações).")
        
    print("\n" + "=" * 66)
    print("       🎉 FLUXO COMPLETO FINALIZADO COM SUCESSO!")
    if yt_url:
        print(f"       🔗 Link no YouTube: {yt_url}")
    print("=" * 66)
    
    summary_line = f"Fluxo Completo Concluído com sucesso! Vídeo: {os.path.basename(video_path)}"
    if yt_url:
        summary_line += f" | YouTube: {yt_url}"
    logger.log_event(project_id, "resumo_projeto", summary_line, level="INFO")

def clean_manager(config):
    """Atalho utilitário para limpeza."""
    return run_step_4_clean_crops(config, non_interactive=False)

def edit_settings(config, config_path=CONFIG_FILE):
    """Tela 2: Menu para alteração interativa de parâmetros de configuração e persistência em JSON."""
    while True:
        crop_label = CROP_MODE_LABELS.get(config.get("crop_mode", "bottom"), config.get("crop_mode", "bottom"))
        source_dir = config.get("source_dir", ".")
        source_display = os.path.abspath(source_dir) if source_dir else os.getcwd()
        if source_dir == ".":
            source_display += " (Diretório Atual)"
        output_dir_display = get_output_dir(config)
        fps = config.get("fps", 60)
        fpi = config.get("frames_per_image", 1)
        dur_photo = fpi / fps if fps > 0 else 0
        auto_clean = config.get("auto_clean_crops", False)
        clean_status = "Ativada (Apaga fotos cortadas após renderizar)" if auto_clean else "Desativada (Mantém fotos cortadas)"
        yt_auto = config.get("youtube_auto_upload", True)
        yt_privacy = config.get("youtube_privacy_status", "unlisted")
        yt_status = "Ativado (Etapa 5 no fluxo completo)" if yt_auto else "Desativado"
        stage_interval = config.get("stage_interval_seconds", 180)
        ntfy_topic = config.get("ntfy_topic", "timelapse-studio-2026")
            
        print("\n" + "="*66)
        print("               CONFIGURAÇÕES DO TIMELAPSE STUDIO")
        print("="*66)
        print(f"[1]  Pasta de Origem (Fotos)      : {source_display}")
        print(f"     ↳ Pasta de Cortes (4K)       : {output_dir_display}")
        print(f"[2]  Taxa de Quadros (FPS)        : {fps} fps")
        print(f"[3]  Frames por Imagem (FPI)      : {fpi} frame(s)/foto ({dur_photo:.2f}s por foto)")
        print(f"[4]  Modo de Corte (Crop 16:9)    : {crop_label}")
        print(f"[5]  Qualidade FFmpeg (CRF)       : {config['crf']} (Menor = melhor qualidade)")
        print(f"[6]  Resolução de saída           : {config['target_width']}x{config['target_height']} (4K UHD)")
        print(f"[7]  Preset FFmpeg                : {config['preset']}")
        print(f"[8]  Limpeza Automática Pós-Vídeo : {clean_status}")
        print(f"[9]  Upload Automático ao YouTube : {yt_status}")
        print(f"[10] Privacidade no YouTube      : {yt_privacy} (unlisted / private / public)")
        print(f"[11] Intervalo entre Etapas (s)  : {stage_interval}s ({stage_interval/60:.1f} min)")
        print(f"[12] Canal de Notificações NTFY  : {ntfy_topic}")
        print(f"[13] Amostragem Modo Teste       : {config['test_sample_size']} fotos")
        custom_tags_disp = ", ".join(config.get("youtube_custom_tags", [])) if config.get("youtube_custom_tags") else "Nenhuma tag definida"
        print(f"[14] Tags Customizadas no YouTube: {custom_tags_disp}")
        print("-" * 66)
        print(f"[S] Salvar Configurações Atuais no '{config_path}'")
        print("[D] Restaurar Configurações Padrão de Fábrica (Reset)")
        print("[0] Voltar ao Menu Principal")
        print("=" * 66)
        
        choice = input("Escolha uma opção [0-14, S ou D]: ").strip().lower()
        if choice == "1":
            select_source_dir(config)
        elif choice == "2":
            quick_change_fps(config)
        elif choice == "3":
            quick_change_fpi(config)
        elif choice == "4":
            quick_change_crop(config)
        elif choice == "5":
            val = input(f"Novo CRF [{config['crf']}]: ").strip()
            if val.isdigit():
                config["crf"] = int(val)
        elif choice == "6":
            w = input(f"Largura [{config['target_width']}]: ").strip()
            h = input(f"Altura [{config['target_height']}]: ").strip()
            if w.isdigit() and h.isdigit():
                config["target_width"] = int(w)
                config["target_height"] = int(h)
        elif choice == "7":
            val = input(f"Novo Preset (ultrafast/medium/slow) [{config['preset']}]: ").strip()
            if val in ["ultrafast", "medium", "slow"]:
                config["preset"] = val
        elif choice == "8":
            config["auto_clean_crops"] = not config.get("auto_clean_crops", False)
            print(f"\n[+] Limpeza automática pós-renderização: {'Ativada' if config['auto_clean_crops'] else 'Desativada'}.")
            time.sleep(1.0)
        elif choice == "9":
            config["youtube_auto_upload"] = not config.get("youtube_auto_upload", True)
            print(f"\n[+] Upload automático ao YouTube: {'Ativado' if config['youtube_auto_upload'] else 'Desativado'}.")
            time.sleep(1.0)
        elif choice == "10":
            print("\nPrivacidade do Vídeo no YouTube:")
            print("  [1] unlisted (Não listado - apenas quem tem o link pode ver - Recomendado)")
            print("  [2] private  (Privado - apenas você pode ver no YouTube Studio)")
            print("  [3] public   (Público - visível para todos no seu canal)")
            p_choice = input(f"Escolha [1/2/3, atual: {yt_privacy}]: ").strip()
            if p_choice == "1":
                config["youtube_privacy_status"] = "unlisted"
            elif p_choice == "2":
                config["youtube_privacy_status"] = "private"
            elif p_choice == "3":
                config["youtube_privacy_status"] = "public"
            print(f"[+] Privacidade alterada para: {config['youtube_privacy_status']}")
            time.sleep(1.0)
        elif choice == "11":
            val = input(f"Intervalo de espera entre etapas em segundos [{config.get('stage_interval_seconds', 180)}]: ").strip()
            if val.isdigit() and int(val) >= 0:
                config["stage_interval_seconds"] = int(val)
                print(f"[+] Intervalo entre etapas alterado para {config['stage_interval_seconds']} segundos.")
                time.sleep(1.0)
        elif choice == "12":
            val = input(f"Novo Canal NTFY [{config.get('ntfy_topic', 'timelapse-studio-2026')}]: ").strip()
            if val:
                config["ntfy_topic"] = val
                print(f"[+] Canal NTFY alterado para: {config['ntfy_topic']}")
                time.sleep(1.0)
        elif choice == "13":
            val = input(f"Nº de Fotos no Teste [{config['test_sample_size']}]: ").strip()
            if val.isdigit():
                config["test_sample_size"] = int(val)
        elif choice == "14":
            current_tags_str = ", ".join(config.get("youtube_custom_tags", []))
            print(f"\nTags customizadas atuais: {current_tags_str or 'Nenhuma'}")
            tags_in = input("Digite as tags personalizadas separadas por vírgula (ou Enter para manter): ").strip()
            if tags_in:
                parsed_tags = [t.strip().lower() for t in tags_in.split(",") if t.strip()]
                config["youtube_custom_tags"] = parsed_tags
                print(f"[+] Tags personalizadas salvas: {', '.join(parsed_tags)}")
                time.sleep(1.0)
        elif choice == "s":
            if save_config(config, config_path):
                print(f"\n[+] Configurações salvas em '{config_path}' com sucesso!")
            time.sleep(1.2)
        elif choice == "d":
            confirm = input("Tem certeza que deseja restaurar os padrões de fábrica? (s/n): ").strip().lower()
            if confirm in ["s", "sim", "y"]:
                config.clear()
                config.update(DEFAULT_CONFIG)
                save_config(config, config_path)
                print("\n[+] Configurações restauradas para os padrões de fábrica!")
                time.sleep(1.2)
        elif choice == "0":
            break

def parse_arguments():
    """Configura e processa os argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description="Timelapse Studio 4K UHD - Processamento e Renderização de Timelapses Multicâmeras."
    )
    parser.add_argument(
        "-c", "--config",
        dest="config_file",
        type=str,
        default=None,
        help=f"Caminho do arquivo de configuração JSON (padrão: {CONFIG_FILE})."
    )
    parser.add_argument(
        "-i", "--input", "--source",
        dest="source_dir",
        type=str,
        default=None,
        help="Caminho da pasta de origem onde estão as fotos JPG/JPEG (suporta caminhos com aspas e drag & drop)."
    )
    parser.add_argument(
        "-fps", "--fps",
        dest="fps",
        type=int,
        default=None,
        help="Taxa de quadros por segundo (ex: 15, 24, 30, 60)."
    )
    parser.add_argument(
        "-fpi", "--fpi", "--frames-per-image",
        dest="frames_per_image",
        type=int,
        default=None,
        help="Número de frames exibidos por cada foto no vídeo (ex: 60 para manter 1 foto/s em 60fps, padrão: 1)."
    )
    parser.add_argument(
        "--crop",
        dest="crop_mode",
        choices=["center", "top", "bottom"],
        default=None,
        help="Modo de enquadramento/corte vertical (center, top, bottom)."
    )
    parser.add_argument(
        "--crf",
        dest="crf",
        type=int,
        default=None,
        help="Fator de qualidade de compressão CRF (menor = melhor qualidade, ex: 15)."
    )
    parser.add_argument(
        "--clean",
        dest="clean",
        action="store_true",
        help="Ativa a limpeza automática das fotos cortadas (Etapa 4)."
    )
    parser.add_argument(
        "--no-clean",
        dest="no_clean",
        action="store_true",
        help="Desativa a limpeza automática das fotos cortadas (Etapa 4)."
    )
    parser.add_argument(
        "--ntfy", "--ntfy-topic",
        dest="ntfy_topic",
        type=str,
        default=None,
        help="Canal/tópico de notificações NTFY (ex: timelapse-studio-2026)."
    )
    parser.add_argument(
        "--no-wizard",
        action="store_true",
        help="Não exibe o assistente interativo de primeira execução caso o arquivo JSON não exista."
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Desativa o upload automático para o YouTube na execução via linha de comando."
    )
    parser.add_argument(
        "--rename-source",
        action="store_true",
        help="Renomeia todas as fotos da pasta de origem com o formato %%Y-%%m-%%d_%%H-%%M-%%S_<nome_original>.jpg e encerra."
    )
    parser.add_argument(
        "--run-all",
        action="store_true",
        help="Executa o pipeline completo (Etapas 1 -> 2 -> 3 -> 4 -> 5) e encerra sem abrir o menu interativo."
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Executa o modo de teste rápido com amostragem reduzida e encerra."
    )
    return parser.parse_args()

def main():
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    args = parse_arguments()
    config_file = args.config_file or CONFIG_FILE
    
    # Carrega config existente ou executa assistente de primeira execução
    config, exists = load_config(config_file)
    
    is_direct_run = bool(args.rename_source or args.run_all or args.test)
    if not exists and not is_direct_run and not args.no_wizard:
        config = interactive_initial_setup_wizard(config_file)
    elif not exists:
        # Se for execução direta com flags, salva valores default para criar o config.json
        save_config(config, config_file)
    
    # Sobrescrita pontual via argumentos CLI
    if args.source_dir:
        cleaned_source = sanitize_path(args.source_dir)
        if os.path.exists(cleaned_source) and os.path.isdir(cleaned_source):
            config["source_dir"] = cleaned_source
        else:
            print(f"[!] Aviso: A pasta de origem informada '{args.source_dir}' não foi encontrada. Usando '{config.get('source_dir')}'.")
            
    if args.fps:
        config["fps"] = args.fps
    if args.frames_per_image and args.frames_per_image > 0:
        config["frames_per_image"] = args.frames_per_image
    if args.crop_mode:
        config["crop_mode"] = args.crop_mode
    if args.crf is not None:
        config["crf"] = args.crf
    if args.no_upload:
        config["youtube_auto_upload"] = False
    if args.no_clean:
        config["auto_clean_crops"] = False
    elif args.clean:
        config["auto_clean_crops"] = True
    if args.ntfy_topic:
        config["ntfy_topic"] = args.ntfy_topic.strip()

    # Renomeação direta via CLI
    if args.rename_source:
        rename_source_photos(config["source_dir"], config["output_dir"], non_interactive=True, config=config)
        return

    # Execuções automáticas diretas via CLI
    if args.run_all:
        print_banner(config)
        run_full_pipeline(config)
        return
        
    if args.test:
        print_banner(config)
        success, _ = run_step_1_crop(config, max_photos=config["test_sample_size"])
        if success:
            run_step_2_video(config, is_test=True)
        return

    # Modo interativo CLI (Tela 1: Menu Principal)
    while True:
        source_dir = config.get("source_dir", ".")
        project_id = logger.get_project_id(source_dir, config.get("output_dir", "fotos_cortadas_4k"))
        print_banner(config, project_id=project_id)
        print("MENU PRINCIPAL:")
        print("  [ENTER] 🚀 EXECUTAR FLUXO COMPLETO (Padrão: Etapas 1 ➔ 2 ➔ 3 ➔ 4 ➔ 5)")
        print("  " + "-" * 58)
        print("  [1] Etapa 1: Organizar e Renomear Fotos de Origem por EXIF")
        print("  [2] Etapa 2: Cortar e Redimensionar Fotos para 4K UHD 16:9 (PIL)")
        print("  [3] Etapa 3: Gerar Vídeo Timelapse 4K (FFmpeg GPU/CPU)")
        print("  [4] Etapa 4: Limpar / Apagar Fotos Cortadas Intermediárias")
        print("  [5] Etapa 5: Publicar Vídeo no YouTube (YouTube Data API v3)")
        print("  [6] Executar Fluxo Completo (Etapas 1 ➔ 2 ➔ 3 ➔ 4 ➔ 5)")
        print("  [7] ⚙️  Menu de Configurações (Pasta, FPS, Corte, CRF, YouTube, etc.)")
        print("  [8] Modo Teste Rápido (Amostra reduzida de 120 fotos)")
        print("  [0] Sair")
        print("=" * 66)
        
        choice = input("Selecione uma opção [0-8 ou pressione ENTER para Fluxo Completo]: ").strip().lower()
        
        if choice in ["", "6"]:
            run_full_pipeline(config)
            input("\nPressione Enter para continuar...")
        elif choice == "1":
            rename_source_photos(config["source_dir"], config["output_dir"], project_id=project_id, config=config)
            input("\nPressione Enter para continuar...")
        elif choice == "2":
            run_step_1_crop(config)
            input("\nPressione Enter para continuar...")
        elif choice == "3":
            run_step_2_video(config)
            input("\nPressione Enter para continuar...")
        elif choice == "4":
            run_step_4_clean_crops(config, non_interactive=False, project_id=project_id)
            input("\nPressione Enter para continuar...")
        elif choice == "5":
            run_step_5_youtube_upload(config, project_id=project_id)
            input("\nPressione Enter para continuar...")
        elif choice == "7":
            edit_settings(config, config_file)
        elif choice == "8":
            run_test_mode(config)
            input("\nPressione Enter para continuar...")
        elif choice == "0":
            print("\n[+] Saindo do Timelapse Studio. Até logo!")
            sys.exit(0)
        else:
            print("\n[-] Opção inválida. Pressione ENTER para fluxo completo ou digite uma opção [0-8].")
            time.sleep(1)

if __name__ == "__main__":
    main()


