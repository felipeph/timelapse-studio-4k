# Timelapse Studio 4K UHD 🎥⚡

Automação em Python para processamento de fotos, renderização de timelapses em **4K UHD (3840x2160)** com suporte a aceleração por hardware (GPU: NVIDIA NVENC, AMD AMF, Intel QSV) e CPU multicore, com **publicação automática no YouTube** via API oficial e **sistema de logs estruturado por projetos**.

---

## 🚀 Funcionalidades

- **Pipeline Completo em 5 Etapas Integradas**:
  1. **Etapa 1 - Organização e Renomeação por EXIF**: Padronização dos nomes das fotos originais para `%Y-%m-%d_%H-%M-%S_<original>.jpg` com base na data/hora do disparo.
  2. **Etapa 2 - Processamento e Corte 4K Paralelo**: Redimensionamento e crop inteligente (Centro, Topo, Base) em 16:9 via `PIL` multicore, preservando metadados EXIF.
  3. **Etapa 3 - Renderização de Vídeo 4K Ultra-rápida**: Detecção automática de aceleração GPU (NVENC/AMF/QSV) com fallback para CPU, injeção de metadados de vídeo e nomenclatura cronológica dinâmica (`timelapse_YYYY-MM-DD_HH-MM---HH-MM.mp4`).
  4. **Etapa 4 - Limpeza Automática Pós-Vídeo**: Remoção automática das fotos cortadas intermediárias após a geração do vídeo para economizar espaço em disco.
  5. **Etapa 5 - Publicação Oficial no YouTube (YouTube Data API v3)**: Upload oficial via protocolo *Resumable Upload* em chunks com barra de progresso em tempo real e retorno do link do vídeo (`https://youtu.be/...`).
- **Sistema de Logs Estruturado por Projeto**: Cada execução do Timelapse Studio é tratada como um projeto, identificado pela data e hora do arquivo mais antigo da fonte (`YYYY-MM-DD_HH-MM-SS`). Registros detalhados por etapa são gravados em `logs/<project_id>/` e consolidados em `logs/timelapse_studio.log`.
- **Execução com 1 Clique (`[ENTER]` Padrão)**: Ao abrir o script, basta pressionar **ENTER** para disparar todo o fluxo sequencial (Etapas 1 ➔ 2 ➔ 3 ➔ 4 ➔ 5).
- **Interface Organizada em 2 Telas**:
  - **Tela 1**: Menu de Execução do Pipeline [0 a 8].
  - **Tela 2 (`[7]`)**: Central de Configurações e Persistência no `config.json`.
- **Gerenciamento Seguro de Credenciais (`secrets/`)**: Armazena as credenciais OAuth do Google Cloud (`secrets/client_secrets.json` e `secrets/token.json`), ambas ignoradas no Git.

---

## 📋 Pré-requisitos

1. **Python 3.8+**
2. **FFmpeg** instalado e adicionado ao `PATH` do sistema.

### Instalação de dependências:

```bash
pip install -r requirements.txt
```

---

## 🔐 Configuração do YouTube (OAuth 2.0)

Para habilitar o envio automático para o seu canal do YouTube:

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Crie um projeto e ative a **YouTube Data API v3**.
3. Na tela de consentimento OAuth, adicione seu e-mail como **Usuário de Teste**.
4. Crie uma credencial do tipo **OAuth client ID** para **Desktop App**.
5. Baixe o arquivo JSON e salve-o em:
   ```text
   secrets/client_secrets.json
   ```
6. Na primeira execução da Etapa 5 ou do Fluxo Completo, o navegador será aberto para você autorizar o acesso uma única vez. O token será salvo em `secrets/token.json`.

---

## 📁 Estrutura de Logs (`logs/`)

```text
timelapse/
├── logs/                         # Ignorado pelo Git
│   ├── timelapse_studio.log      # Histórico consolidado de todos os projetos
│   └── 2026-08-29_08-15-30/      # Pasta do projeto (data da 1ª foto)
│       ├── resumo_projeto.log
│       ├── etapa_1_rename.log
│       ├── etapa_2_crop.log
│       ├── etapa_3_video.log
│       ├── etapa_4_clean.log
│       └── etapa_5_youtube.log
```

---

## ⚙️ Configurações & Arquivo `config.json`

O Timelapse Studio suporta carregamento automático de opções através de um arquivo `config.json`.

### Modelo de Configuração (`config.example.json`):
```json
{
  "source_dir": ".",
  "output_dir": "fotos_cortadas_4k",
  "fps": 60,
  "frames_per_image": 1,
  "crop_mode": "center",
  "crf": 15,
  "preset": "ultrafast",
  "target_width": 3840,
  "target_height": 2160,
  "test_sample_size": 120,
  "auto_clean_crops": true,
  "youtube_auto_upload": true,
  "youtube_privacy_status": "unlisted",
  "youtube_category_id": "22"
}
```

---

## 🛠️ Como Usar

### 1. Modo Interativo (Menu CLI em 2 Telas)

Execute o script principal:

```bash
python timelapse_studio.py
```

#### Tela 1: Menu Principal
- **Pressione `[ENTER]` ou `[6]`**: Dispara o **Fluxo Completo** (Etapas 1 ➔ 2 ➔ 3 ➔ 4 ➔ 5).
- `[1]`: Etapa 1 - Organizar e renomear fotos de origem por EXIF.
- `[2]`: Etapa 2 - Cortar e redimensionar fotos para 4K UHD.
- `[3]`: Etapa 3 - Gerar o vídeo timelapse 4K.
- `[4]`: Etapa 4 - Limpar/apagar a pasta de fotos cortadas intermediárias.
- `[5]`: Etapa 5 - Publicar vídeo no YouTube via API oficial.
- `[6]`: Executar Fluxo Completo (Etapas 1 a 5).
- `[7]`: ⚙️ Abrir a **Tela 2 de Configurações**.
- `[8]`: Modo Teste Rápido (amostra de 120 fotos).
- `[0]`: Sair.

#### Tela 2: Menu de Configurações (Opção `[7]`)
- Altere Pasta de Origem, FPS, Frames por Imagem (FPI), Modo de Corte, CRF, Resolução e Preset.
- Ative/Desative a Limpeza Automática pós-vídeo (`[8]`).
- Ative/Desative o Upload Automático para o YouTube (`[9]`) e Privacidade (`[10]`: unlisted / private / public).
- Pressione `[S]` para salvar no `config.json` ou `[D]` para restaurar padrões de fábrica.

---

### 2. Linha de Comando (Modo Direto / Automação)

```bash
# Executar o fluxo completo automatizado (Etapas 1 a 5)
python timelapse_studio.py -i "D:\Fotos\GoPro_Viagem" -fps 60 -fpi 60 --run-all

# Executar o fluxo completo sem upload para o YouTube
python timelapse_studio.py -i "D:\Fotos\GoPro_Viagem" --run-all --no-upload

# Renomear fotos da pasta de origem pelo EXIF e sair
python timelapse_studio.py -i "D:\Fotos\GoPro_Viagem" --rename-source

# Executar modo de teste rápido
python timelapse_studio.py -i "C:\Imagens\Timelapse" --test
```
