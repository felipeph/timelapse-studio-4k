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
import glob
import time
import json
import argparse
import datetime
import subprocess
import concurrent.futures
from PIL import Image, ExifTags

CONFIG_FILE = "config.json"

# Configurações Padrão
DEFAULT_CONFIG = {
    "source_dir": ".",
    "target_width": 3840,
    "target_height": 2160,
    "fps": 60,
    "frames_per_image": 1,
    "crf": 15,
    "preset": "ultrafast",
    "crop_mode": "center",
    "output_dir": "fotos_cortadas_4k",
    "output_video": "timelapse_4k_cortado.mp4",
    "test_sample_size": 120,
    "test_output_video": "timelapse_teste_4k.mp4"
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
            "target_height", "test_sample_size", "output_video", "test_output_video"
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
    print("   [1] Centro (Corta topo e base igualmente - Padrão)")
    print("   [2] Topo (Preserva topo, apaga base)")
    print("   [3] Base (Preserva base, apaga topo)")
    crop_choice = input(f"   Escolha [1/2/3 ou Enter para Centro]: ").strip()
    if crop_choice == "2":
        config["crop_mode"] = "top"
    elif crop_choice == "3":
        config["crop_mode"] = "bottom"
    else:
        config["crop_mode"] = "center"
        
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

def print_banner(config=None):
    """Exibe o cabeçalho decorado do programa e as configurações atuais ativas."""
    print("=" * 66)
    print("                TIMELAPSE STUDIO 4K UHD")
    print("   Automação Multicâmeras (GoPro, Canon, etc.) & Renderização")
    print("=" * 66)
    if config:
        crop_mode = config.get("crop_mode", "center")
        crop_label = CROP_MODE_LABELS.get(crop_mode, crop_mode)
        source_dir = config.get("source_dir", ".")
        source_display = os.path.abspath(source_dir) if source_dir else os.getcwd()
        if source_dir == ".":
            source_display += " (Diretório Atual)"
        output_dir_display = get_output_dir(config)
        fps = config.get("fps", 60)
        fpi = config.get("frames_per_image", 1)
        dur_per_photo = fpi / fps if fps > 0 else 0
            
        print(" CONFIGURAÇÕES ATUAIS:")
        print(f"   • Pasta de Origem (Fotos): {source_display}")
        print(f"   • Pasta de Cortes (4K)   : {output_dir_display}")
        print(f"   • Taxa de Quadros (FPS)  : {fps} fps")
        print(f"   • Frames por Imagem (FPI): {fpi} frame(s)/foto ({dur_per_photo:.2f}s por foto)")
        print(f"   • Modo de Corte (Crop)    : {crop_label}")
        print(f"   • Qualidade (CRF)         : {config['crf']} (Menor = melhor qualidade)")
        print(f"   • Resolução Alvo          : {config['target_width']}x{config['target_height']} (4K UHD)")
        print(f"   • Amostra Modo Teste      : {config['test_sample_size']} fotos")
        print("=" * 66)

def print_progress_bar(current, total, start_time, prefix="Progresso"):
    """Exibe uma barra de progresso formatada com caracteres ASCII seguros no terminal."""
    percent = current / total if total > 0 else 1.0
    bar_length = 28
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
        
    sys.stdout.write(
        f"\r{prefix}: [{hashes}{spaces}] {percent*100:.1f}% | "
        f"{current}/{total} | "
        f"{fps:.1f} it/s | "
        f"Tempo: {elapsed_str} | ETA: {eta_str}"
    )
    sys.stdout.flush()

def get_exif_datetime(img_path):
    """Extrai a data/hora original da foto via cabeçalhos EXIF como objeto datetime."""
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

def format_photo_name(img_path, dt=None):
    """
    Gera o nome da foto no formato: %Y-%m-%d_%H-%M-%S_<nome_original>.jpg
    Se o arquivo já possuir o prefixo no padrão esperado, mantém para evitar duplicações.
    """
    if dt is None:
        dt = get_exif_datetime(img_path)
    ts_prefix = dt.strftime('%Y-%m-%d_%H-%M-%S')
    base_name = os.path.basename(img_path)
    name_no_ext, ext = os.path.splitext(base_name)
    
    # Verifica se já começa com o padrão YYYY-MM-DD_HH-MM-SS_
    if len(name_no_ext) >= 20 and name_no_ext[4] == '-' and name_no_ext[7] == '-' and name_no_ext[10] == '_' and name_no_ext[13] == '-' and name_no_ext[16] == '-':
        return f"{name_no_ext}{ext.lower()}"
        
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

def rename_source_photos(source_dir, output_dir_name="fotos_cortadas_4k", non_interactive=False):
    """
    Renomeia todas as fotos JPG/JPEG na pasta de origem com a data/hora do EXIF:
    %Y-%m-%d_%H-%M-%S_<nome_original>.jpg
    """
    photos = find_all_photos(source_dir, output_dir_name)
    if not photos:
        print(f"\n[-] Nenhuma foto encontrada em {os.path.abspath(source_dir)} para renomear.")
        return 0
        
    print("\n" + "=" * 66)
    print("      ORGANIZAÇÃO E RENOMEAÇÃO DE FOTOS POR EXIF")
    print("=" * 66)
    print(f"[+] Pasta de origem: {os.path.abspath(source_dir)}")
    print(f"[+] Total de fotos encontradas: {len(photos)}")
    print("[+] Formato alvo: %Y-%m-%d_%H-%M-%S_<nome_original>.jpg")
    print("-" * 66)
    
    if not non_interactive:
        confirm = input("Deseja prosseguir com a renomeação dos arquivos de origem? (s/N): ").strip().lower()
        if confirm != 's':
            print("[+] Operação cancelada pelo usuário.")
            return 0
            
    renamed_count = 0
    for img_path in photos:
        dir_name = os.path.dirname(img_path)
        old_filename = os.path.basename(img_path)
        new_filename = format_photo_name(img_path)
        
        if old_filename != new_filename:
            new_path = os.path.join(dir_name, new_filename)
            if not os.path.exists(new_path):
                try:
                    os.rename(img_path, new_path)
                    renamed_count += 1
                except Exception as e:
                    print(f"[-] Erro ao renomear {old_filename}: {e}")
                    
    print(f"[+] Concluído! {renamed_count} arquivos renomeados com sucesso.")
    print("=" * 66)
    return renamed_count

def process_single_image(task):
    """
    Worker executado em paralelo para cortar 16:9 (centralizado, por baixo ou por cima)
    e redimensionar/ajustar para a resolução alvo (ex: 3840x2160 4K),
    preservando os metadados EXIF e o nome base com o sufixo _crop4k.jpg.
    task = (img_path, output_dir, target_w, target_h, seq_idx, crop_mode)
    """
    img_path, output_dir, target_w, target_h, seq_idx, crop_mode = task
    try:
        dt = get_exif_datetime(img_path)
        formatted_name = format_photo_name(img_path, dt=dt)
        name_no_ext, _ = os.path.splitext(formatted_name)
        
        # Nome do arquivo final: %Y-%m-%d_%H-%M-%S_nomeoriginal_crop4k.jpg
        out_filename = f"{name_no_ext}_crop4k.jpg"
        out_path = os.path.join(output_dir, out_filename)
        
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
            
        return True, out_path
    except Exception as e:
        return False, f"Erro em {os.path.basename(img_path)}: {str(e)}"

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
    
    crop_mode = config.get("crop_mode", "center")
    crop_label = CROP_MODE_LABELS.get(crop_mode, crop_mode)
    
    total = len(all_photos)
    print("\n" + "="*66)
    print("        ETAPA 1: CORTE 16:9 E REDIMENSIONAMENTO 4K (PIL)")
    print("="*66)
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
    errors = 0

    with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = [executor.submit(process_single_image, t) for t in tasks]
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            success, res = future.result()
            if not success:
                errors += 1
            print_progress_bar(completed, total, start_time, prefix="Processando fotos")

    print() # Pular linha
    total_time = time.time() - start_time
    print("-" * 66)
    if errors == 0:
        print(f"[+] Sucesso! {completed} fotos processadas em {total_time:.1f} segundos ({completed/total_time:.1f} fotos/s).")
    else:
        print(f"[!] Concluído com {errors} erros de {completed} fotos processadas.")
        
    print(f"[+] Fotos salvas em: {output_dir}")
    print("=" * 66)
    return True, output_dir

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
            print_progress_bar(idx + 1, total_photos, start_time, prefix="Renderizando vídeo")
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
    """Etapa 2: Gerar o vídeo timelapse 4K com suporte a fallback automático para CPU e metadados."""
    input_dir = get_output_dir(config)
    source_dir = config.get("source_dir", ".")
    
    if not os.path.exists(input_dir):
        print(f"\n[-] Erro: A pasta '{input_dir}' não foi encontrada.")
        print("    Por favor, execute a Etapa 1 primeiro para gerar as fotos cortadas.")
        return False

    pattern = os.path.join(input_dir, "*.jpg")
    cropped_photos = sorted(glob.glob(pattern))

    if not cropped_photos:
        print(f"\n[-] Erro: Nenhuma imagem JPG encontrada na pasta '{input_dir}'.")
        return False

    video_name, first_dt, last_dt, range_str = generate_video_info(cropped_photos, is_test=is_test)
    output_path = os.path.abspath(os.path.join(source_dir, video_name))

    # Primeira tentativa (utiliza GPU se disponível)
    success, encoder_used = render_video_ffmpeg(
        config, cropped_photos, output_path, force_cpu=False,
        first_dt=first_dt, last_dt=last_dt, range_str=range_str
    )
    
    # Se a GPU (ex: Intel QSV) falhar, faz fallback automático transparente para CPU (libx264)
    if not success and "CPU" not in encoder_used:
        print("\n[!] TENTANDO RENDERIZAR VIA CPU (libx264) COMO FALLBACK DE SEGURANÇA...")
        success, _ = render_video_ffmpeg(
            config, cropped_photos, output_path, force_cpu=True,
            first_dt=first_dt, last_dt=last_dt, range_str=range_str
        )
        
    return success

def quick_change_crop(config):
    """Menu de atalho rápido para alterar a posição de enquadramento/corte (crop 16:9)."""
    current_mode = config.get("crop_mode", "center")
    print("\n" + "="*66)
    print("             AJUSTE DE ENQUADRAMENTO / CORTE (CROP 16:9)")
    print("="*66)
    print(f"Modo atual: {CROP_MODE_LABELS.get(current_mode, current_mode)}")
    print("\nEscolha a posição do enquadramento vertical:")
    print("  [1] Centro    (Corta igualmente o topo e a base - Padrão)")
    print("  [2] Por Baixo (Preserva a base, apaga o topo - Foco no chão/pessoas)")
    print("  [3] Por Cima  (Preserva o topo, apaga a base - Foco no céu/paisagem)")
    print("  [0] Cancelar / Manter modo atual")
    print("-" * 66)
    
    choice = input("Escolha uma opção [0-3]: ").strip()
    if choice == "1":
        config["crop_mode"] = "center"
        print(f"[+] Modo de corte alterado para: {CROP_MODE_LABELS['center']}")
    elif choice == "2":
        config["crop_mode"] = "bottom"
        print(f"[+] Modo de corte alterado para: {CROP_MODE_LABELS['bottom']}")
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
    """Executa as Etapas 1 e 2 em modo de teste rápido com amostragem reduzida e confirmação de parâmetros."""
    crop_short = {"center": "Centro", "bottom": "Por Baixo", "top": "Por Cima"}.get(config.get("crop_mode", "center"), "Centro")
    fps = config.get("fps", 60)
    fpi = config.get("frames_per_image", 1)
    dur_photo = fpi / fps if fps > 0 else 0
    print(f"\n[!] INICIANDO MODO TESTE RÁPIDO ({config['test_sample_size']} FOTOS)")
    print(f"    FPS: {fps} fps | Frames/Foto: {fpi} ({dur_photo:.2f}s/foto) | Corte: {crop_short}")
    
    change_prompt = input("Deseja alterar FPS/Frames por Foto, Pasta de Origem ou Modo de Corte antes do teste? (s/N): ").strip().lower()
    if change_prompt == 's':
        select_source_dir(config)
        quick_change_fps(config)
        quick_change_fpi(config)
        quick_change_crop(config)
        
    success, _ = run_step_1_crop(config, max_photos=config["test_sample_size"])
    if success:
        run_step_2_video(config, is_test=True)

def run_full_pipeline(config):
    """Executa o fluxo completo (Etapa 1 + Etapa 2 sequencialmente)."""
    crop_short = {"center": "Centro", "bottom": "Por Baixo", "top": "Por Cima"}.get(config.get("crop_mode", "center"), "Centro")
    fps = config.get("fps", 60)
    fpi = config.get("frames_per_image", 1)
    dur_photo = fpi / fps if fps > 0 else 0
    print("\n[!] INICIANDO FLUXO COMPLETO (ETAPA 1 + ETAPA 2)")
    print(f"    Configuração: {fps} FPS | {fpi} frame(s)/foto ({dur_photo:.2f}s/foto) | {config['target_width']}x{config['target_height']} | CRF {config['crf']} | Corte: {crop_short}")
    
    success, _ = run_step_1_crop(config)
    if success:
        run_step_2_video(config, is_test=False)

def clean_manager(config):
    """Menu utilitário para limpeza de fotos cortadas e arquivos temporários."""
    output_dir = get_output_dir(config)
    
    while True:
        print("\n" + "="*66)
        print("             GERENCIADOR DE LIMPEZA E ARQUIVOS")
        print("="*66)
        
        has_cropped = os.path.exists(output_dir)
        cropped_count = len(glob.glob(os.path.join(output_dir, "*.jpg"))) if has_cropped else 0
        cropped_size_mb = 0
        if has_cropped:
            for f in glob.glob(os.path.join(output_dir, "*.jpg")):
                cropped_size_mb += os.path.getsize(f) / (1024 * 1024)
                
        print(f"[1] Fotos cortadas em '{output_dir}': {cropped_count} arquivos ({cropped_size_mb:.2f} MB)")
        print("[2] Apagar a pasta de fotos cortadas")
        print("[0] Voltar ao Menu Principal")
        print("-" * 66)
        
        choice = input("Escolha uma opção: ").strip()
        if choice == "2":
            if has_cropped:
                confirm = input(f"Tem certeza que deseja apagar a pasta '{output_dir}'? (s/N): ").strip().lower()
                if confirm == 's':
                    import shutil
                    shutil.rmtree(output_dir)
                    print(f"[+] Pasta '{output_dir}' removida com sucesso!")
            else:
                print("[!] A pasta de fotos cortadas já não existe.")
        elif choice == "0":
            break

def edit_settings(config, config_path=CONFIG_FILE):
    """Menu para alteração interativa de parâmetros de configuração e persistência em JSON."""
    while True:
        crop_label = CROP_MODE_LABELS.get(config.get("crop_mode", "center"), config.get("crop_mode", "center"))
        source_dir = config.get("source_dir", ".")
        source_display = os.path.abspath(source_dir) if source_dir else os.getcwd()
        if source_dir == ".":
            source_display += " (Diretório Atual)"
        output_dir_display = get_output_dir(config)
        fps = config.get("fps", 60)
        fpi = config.get("frames_per_image", 1)
        dur_photo = fpi / fps if fps > 0 else 0
            
        print("\n" + "="*66)
        print("               CONFIGURAÇÕES DO TIMELAPSE STUDIO")
        print("="*66)
        print(f"[1] Pasta de Origem (Fotos) : {source_display}")
        print(f"    ↳ Pasta de Cortes (4K)  : {output_dir_display}")
        print(f"[2] Taxa de Quadros (FPS)   : {fps} fps")
        print(f"[3] Frames por Imagem (FPI) : {fpi} frame(s)/foto ({dur_photo:.2f}s por foto)")
        print(f"[4] Modo de Corte (Crop)     : {crop_label}")
        print(f"[5] Qualidade FFmpeg (CRF)   : {config['crf']}")
        print(f"[6] Resolução de saída       : {config['target_width']}x{config['target_height']}")
        print(f"[7] Amostragem Modo Teste    : {config['test_sample_size']} fotos")
        print(f"[8] Preset FFmpeg            : {config['preset']}")
        print(f"[S] Salvar Configurações Atuais no '{config_path}'")
        print("[D] Restaurar Configurações Padrão de Fábrica (Reset)")
        print("[0] Voltar ao Menu Principal")
        print("-" * 66)
        
        choice = input("Escolha uma opção para alterar [0-8, S ou D]: ").strip().lower()
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
            val = input(f"Nº de Fotos no Teste [{config['test_sample_size']}]: ").strip()
            if val.isdigit():
                config["test_sample_size"] = int(val)
        elif choice == "8":
            val = input(f"Novo Preset (ultrafast/medium/slow) [{config['preset']}]: ").strip()
            if val in ["ultrafast", "medium", "slow"]:
                config["preset"] = val
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
        default=CONFIG_FILE,
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
        "--no-wizard",
        action="store_true",
        help="Não exibe o assistente interativo de primeira execução caso o arquivo JSON não exista."
    )
    parser.add_argument(
        "--rename-source",
        action="store_true",
        help="Renomeia todas as fotos da pasta de origem com o formato %%Y-%%m-%%d_%%H-%%M-%%S_<nome_original>.jpg e encerra."
    )
    parser.add_argument(
        "--run-all",
        action="store_true",
        help="Executa o pipeline completo (Etapa 1 + Etapa 2) e encerra sem abrir o menu interativo."
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Executa o modo de teste rápido com amostragem reduzida e encerra."
    )
    return parser.parse_args()

def main():
    args = parse_arguments()
    config_file = args.config_file
    
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

    # Renomeação direta via CLI
    if args.rename_source:
        rename_source_photos(config["source_dir"], config["output_dir"], non_interactive=True)
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

    # Modo interativo CLI
    while True:
        crop_short = {"center": "Centro", "bottom": "Por Baixo", "top": "Por Cima"}.get(config.get("crop_mode", "center"), "Centro")
        fps = config.get("fps", 60)
        fpi = config.get("frames_per_image", 1)
        dur_photo = fpi / fps if fps > 0 else 0
        print_banner(config)
        print("MENU PRINCIPAL:")
        print("  [1] Etapa 1: Cortar e Redimensionar Fotos para 4K UHD 16:9 (PIL)")
        print("  [2] Etapa 2: Gerar Vídeo Timelapse 4K (FFmpeg GPU/CPU)")
        print("  [3] Modo Teste Rápido (Amostra de 120 fotos)")
        print("  [4] Executar Fluxo Completo (Etapa 1 + Etapa 2 Sequencialmente)")
        print("  [R] Organizar/Renomear Fotos de Origem por EXIF (%Y-%m-%d_%H-%M-%S)")
        print("  [O] Definir/Alterar Pasta de Origem (Fotos)")
        print(f"  [C] Alterar Modo de Corte (Atual: {crop_short})")
        print(f"  [F] Alterar FPS Rapidamente (FPS Atual: {fps} fps)")
        print(f"  [P] Alterar Frames por Imagem (Atual: {fpi} frame(s)/foto | {dur_photo:.2f}s/foto)")
        print("  [5] Menu de Configurações Avançadas & Persistência (CRF, Preset, JSON)")
        print("  [6] Gerenciador de Limpeza de Arquivos")
        print("  [0] Sair")
        print("=" * 66)
        
        choice = input("Selecione uma opção [0-6, R, O, C, F ou P]: ").strip().lower()
        
        if choice == "1":
            run_step_1_crop(config)
            input("\nPressione Enter para continuar...")
        elif choice == "2":
            run_step_2_video(config)
            input("\nPressione Enter para continuar...")
        elif choice == "3":
            run_test_mode(config)
            input("\nPressione Enter para continuar...")
        elif choice == "4":
            run_full_pipeline(config)
            input("\nPressione Enter para continuar...")
        elif choice == "r":
            rename_source_photos(config["source_dir"], config["output_dir"])
            input("\nPressione Enter para continuar...")
        elif choice in ["o", "d"]:
            select_source_dir(config)
            input("\nPressione Enter para continuar...")
        elif choice == "c":
            quick_change_crop(config)
            input("\nPressione Enter para continuar...")
        elif choice == "f":
            quick_change_fps(config)
            input("\nPressione Enter para continuar...")
        elif choice == "p":
            quick_change_fpi(config)
            input("\nPressione Enter para continuar...")
        elif choice == "5":
            edit_settings(config, config_file)
        elif choice == "6":
            clean_manager(config)
        elif choice == "0":
            print("\n[+] Saindo do Timelapse Studio. Até logo!")
            sys.exit(0)
        else:
            print("\n[-] Opção inválida. Digite um número de 0 a 6, R, O, C, F ou P.")
            time.sleep(1)

if __name__ == "__main__":
    main()


