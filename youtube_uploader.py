#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MÓDULO DE UPLOAD OFICIAL PARA O YOUTUBE - TIMELAPSE STUDIO 4K
------------------------------------------------------------
Utiliza o Google API Python Client com OAuth 2.0 e o protocolo oficial Resumable Upload
com suporte a arquivos 4K pesados, barra de progresso em tempo real e renovação de tokens.
"""

import os
import sys
import time
import socket
import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

import logger

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
SECRETS_DIR = "secrets"

def find_client_secrets_file():
    """Procura pelo arquivo client_secrets.json na pasta secrets/ ou na raiz."""
    candidates = [
        os.path.join(SECRETS_DIR, "client_secrets.json"),
        "client_secrets.json"
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return None

def find_token_file():
    """Retorna o caminho do arquivo token.json (preferencialmente dentro de secrets/)."""
    os.makedirs(SECRETS_DIR, exist_ok=True)
    return os.path.abspath(os.path.join(SECRETS_DIR, "token.json"))

def get_authenticated_service(project_id=None):
    """
    Autentica com a YouTube Data API v3 usando OAuth 2.0.
    Gera ou renova o token.json em secrets/ e abre o navegador se necessário.
    """
    creds = None
    token_path = find_token_file()
    
    # 1. Carrega credenciais salvas previamente
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception as e:
            logger.log_event(project_id, "etapa_5_youtube", f"Erro ao ler token.json: {e}", level="WARN")
            creds = None
            
    # 2. Se não existem credenciais válidas, atualiza ou solicita login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("\n[+] Renovando token de autenticação do YouTube...")
                creds.refresh(Request())
                with open(token_path, "w", encoding="utf-8") as token_file:
                    token_file.write(creds.to_json())
                logger.log_event(project_id, "etapa_5_youtube", "Token OAuth renovado com sucesso.")
            except Exception as e:
                print(f"[!] Falha ao renovar token ({e}). Solicitando nova autorização no navegador...")
                creds = None
                
        if not creds:
            client_secrets_path = find_client_secrets_file()
            if not client_secrets_path:
                msg = (
                    "Arquivo 'client_secrets.json' não encontrado!\n"
                    "Coloque o arquivo de credenciais OAuth baixado do Google Cloud na pasta 'secrets/client_secrets.json'."
                )
                print(f"\n[-] ERRO: {msg}")
                logger.log_event(project_id, "etapa_5_youtube", msg, level="ERROR")
                return None
                
            print("\n" + "=" * 66)
            print("         AUTENTICAÇÃO OFICIAL DO YOUTUBE (OAUTH 2.0)")
            print("=" * 66)
            print(" 1. Uma janela do seu navegador será aberta para autorizar o envio de vídeos.")
            print(" 2. Selecione a sua conta Google / Canal do YouTube e clique em 'Permitir'.")
            print(" 3. O token será salvo com segurança em 'secrets/token.json'.")
            print("=" * 66)
            
            try:
                flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
                creds = flow.run_local_server(port=0, prompt='consent')
                with open(token_path, "w", encoding="utf-8") as token_file:
                    token_file.write(creds.to_json())
                print("[+] Autenticação concluída e salva com sucesso!")
                logger.log_event(project_id, "etapa_5_youtube", "Primeira autenticação OAuth realizada com sucesso.")
            except Exception as e:
                msg = f"Falha no fluxo de login OAuth: {e}"
                print(f"[-] {msg}")
                logger.log_event(project_id, "etapa_5_youtube", msg, level="ERROR")
                return None
                
    try:
        # Define timeout de socket mais tolerante para uploads pesados
        socket.setdefaulttimeout(300)
        return build("youtube", "v3", credentials=creds)
    except Exception as e:
        msg = f"Erro ao inicializar cliente da YouTube API: {e}"
        print(f"[-] {msg}")
        logger.log_event(project_id, "etapa_5_youtube", msg, level="ERROR")
        return None

def upload_video_resumable(video_path, metadata=None, project_id=None):
    """
    Realiza o upload do vídeo 4K para o YouTube usando o protocolo oficial Resumable Upload em chunks.
    Retorna (sucesso: bool, video_url: str ou None, video_id: str ou None).
    """
    if not os.path.exists(video_path):
        msg = f"Arquivo de vídeo não encontrado para upload: {video_path}"
        print(f"[-] {msg}")
        logger.log_event(project_id, "etapa_5_youtube", msg, level="ERROR")
        return False, None, None
        
    youtube = get_authenticated_service(project_id)
    if not youtube:
        return False, None, None
        
    metadata = metadata or {}
    title = metadata.get("title", f"Timelapse 4K UHD - {os.path.basename(video_path)}")
    description = metadata.get("description", "Vídeo Timelapse processado e renderizado em 4K UHD pelo Timelapse Studio.")
    tags = metadata.get("tags", ["timelapse", "4k", "timelapse studio", "uhd"])
    category_id = metadata.get("category_id", "22") # 22 = People & Blogs
    privacy_status = metadata.get("privacy_status", "unlisted") # unlisted, private, public
    
    file_size = os.path.getsize(video_path)
    file_size_mb = file_size / (1024 * 1024)
    
    print("\n" + "=" * 66)
    print("      ETAPA 5: PUBLICANDO VÍDEO NO YOUTUBE (API OFICIAL)")
    print("=" * 66)
    print(f" Arquivo    : {os.path.basename(video_path)} ({file_size_mb:.2f} MB)")
    print(f" Título     : {title}")
    print(f" Privacidade: {privacy_status.upper()}")
    print(f" Categoria  : {category_id}")
    print("-" * 66)
    
    logger.log_event(
        project_id, "etapa_5_youtube",
        f"Iniciando upload de '{video_path}' ({file_size_mb:.2f} MB) | Título: '{title}' | Privacidade: {privacy_status}"
    )
    
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags,
            "categoryId": str(category_id)
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False
        }
    }
    
    # Chunk size: 8 MB (múltiplo de 256 KB exigido pelo YouTube)
    chunk_size = 8 * 1024 * 1024
    media = MediaFileUpload(video_path, chunksize=chunk_size, resumable=True)
    
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media
    )
    
    response = None
    start_time = time.time()
    retry_count = 0
    max_retries = 10
    
    print("Enviando vídeo...")
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                progress = status.progress()
                percent = progress * 100
                bar_len = 28
                hashes = '=' * int(round(progress * bar_len))
                spaces = '-' * (bar_len - len(hashes))
                
                elapsed = time.time() - start_time
                bytes_sent = status.total_size * progress if status.total_size else 0
                mb_sent = bytes_sent / (1024 * 1024)
                total_mb = status.total_size / (1024 * 1024) if status.total_size else file_size_mb
                
                speed_mb_s = mb_sent / elapsed if elapsed > 0 else 0
                eta_s = (total_mb - mb_sent) / speed_mb_s if speed_mb_s > 0 else 0
                
                elapsed_str = time.strftime("%M:%S", time.gmtime(elapsed))
                eta_str = time.strftime("%M:%S", time.gmtime(eta_s))
                
                sys.stdout.write(
                    f"\rUpload YouTube: [{hashes}{spaces}] {percent:.1f}% | "
                    f"{mb_sent:.1f}/{total_mb:.1f} MB | {speed_mb_s:.2f} MB/s | "
                    f"Tempo: {elapsed_str} | ETA: {eta_str}"
                )
                sys.stdout.flush()
                retry_count = 0
        except HttpError as e:
            if e.resp.status in [500, 502, 503, 504] and retry_count < max_retries:
                retry_count += 1
                sleep_time = min(2 ** retry_count, 60)
                print(f"\n[!] Erro de rede ({e.resp.status}). Tentativa {retry_count}/{max_retries} em {sleep_time}s...")
                time.sleep(sleep_time)
            else:
                msg = f"Erro na API do YouTube ({e.resp.status}): {e.content.decode('utf-8', errors='ignore')}"
                print(f"\n[-] {msg}")
                logger.log_event(project_id, "etapa_5_youtube", msg, level="ERROR")
                return False, None, None
        except Exception as e:
            if retry_count < max_retries:
                retry_count += 1
                sleep_time = min(2 ** retry_count, 60)
                print(f"\n[!] Conexão oscilou ({e}). Retomando upload ({retry_count}/{max_retries}) em {sleep_time}s...")
                time.sleep(sleep_time)
            else:
                msg = f"Falha irrecuperável no upload: {e}"
                print(f"\n[-] {msg}")
                logger.log_event(project_id, "etapa_5_youtube", msg, level="ERROR")
                return False, None, None

    sys.stdout.write("\n")
    if response and "id" in response:
        video_id = response["id"]
        video_url = f"https://youtu.be/{video_id}"
        total_time = time.time() - start_time
        total_time_str = time.strftime("%M:%S", time.gmtime(total_time))
        
        print("=" * 66)
        print("         🎉 VÍDEO PUBLICADO COM SUCESSO NO YOUTUBE!")
        print("=" * 66)
        print(f" Link do Vídeo : {video_url}")
        print(f" ID do Vídeo   : {video_id}")
        print(f" Privacidade  : {privacy_status.upper()}")
        print(f" Tempo de Envio: {total_time_str}")
        print("=" * 66)
        
        success_msg = f"Vídeo publicado com sucesso! ID: {video_id} | URL: {video_url} | Tempo: {total_time_str}"
        logger.log_event(project_id, "etapa_5_youtube", success_msg, level="INFO")
        logger.log_event(project_id, "resumo_projeto", f"YouTube: {video_url} ({privacy_status})", level="INFO")
        return True, video_url, video_id
    else:
        msg = f"Resposta inesperada do YouTube: {response}"
        print(f"[-] {msg}")
        logger.log_event(project_id, "etapa_5_youtube", msg, level="ERROR")
        return False, None, None
