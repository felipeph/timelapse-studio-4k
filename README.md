# Timelapse Studio 4K UHD 🎥⚡

Automação em Python para processamento de fotos e renderização de timelapses em **4K UHD (3840x2160)** com suporte a aceleração por hardware (GPU: NVIDIA NVENC, AMD AMF, Intel QSV) e CPU multicore.

---

## 🚀 Funcionalidades

- **Multicâmeras**: Compatível com GoPro, Canon, Nikon, Sony e qualquer câmera (busca automática em subpastas `DCIM` ou na raiz).
- **Pasta de Origem Personalizada**: Suporte para definir e alterar o diretório onde estão as fotos (com suporte a drag & drop no terminal do Windows).
- **Organização e Renomeação por EXIF**: Padronização dos nomes das fotos para `%Y-%m-%d_%H-%M-%S_<nome_original>.jpg` com base na data/hora do cabeçalho EXIF.
- **Processamento 4K Paralelo com Preservação EXIF**: Redimensionamento e crop inteligente (Centro, Topo, Base) utilizando todos os núcleos da CPU via `concurrent.futures`, mantendo os dados EXIF no arquivo recortado com o sufixo `_crop4k.jpg`.
- **Nomenclatura Dinâmica de Vídeos**: Arquivo de vídeo nomeado automaticamente com base no intervalo cronológico das capturas (`timelapse_YYYY-MM-DD_HH-MM---HH-MM.mp4`).
- **Injeção de Metadados nos Vídeos**: Tags de contêiner MP4 (`creation_time`, `date`, `title`, `comment`) preenchidas automaticamente com a data e hora do início das fotos.
- **Renderização Rápida**: Detecção automática de aceleração por GPU (NVENC / AMF / QSV) com fallback transparente para CPU (`libx264`/`libx265`).
- **Menu Interativo CLI**:
  - Organizar/renomear fotos de origem por EXIF (`[R]`).
  - Seleção e troca da pasta de origem das fotos (`[O]`).
  - Teste rápido de renderização (amostra de fotos).
  - Ajuste dinâmico de taxa de quadros (FPS: 24, 30, 60, etc.).
  - Configuração de modo de enquadramento (Crop).
  - Pipeline automatizado de ponta a ponta.

---

## 📋 Pré-requisitos

1. **Python 3.8+**
2. **FFmpeg** instalado e adicionado ao `PATH` do sistema.

### Instalação de dependências:

```bash
pip install -r requirements.txt
```

---

## 🛠️ Como Usar

### 1. Modo Interativo (Menu CLI)

Execute o script principal:

```bash
python timelapse_studio.py
```

Siga as opções do menu interativo no terminal:
- Pressione `[R]` para renomear suas fotos de origem pelo timestamp do EXIF.
- Pressione `[O]` para definir ou alterar a pasta de origem das fotos (arrastando a pasta para a janela do terminal).
- Pressione `[1]` para processar os cortes 4K e `[2]` para gerar o vídeo final com metadados e nome cronológico.

### 2. Linha de Comando (Modo Direto / Automação)

Você também pode passar argumentos diretamente via linha de comando:

```bash
# Renomear fotos da pasta de origem pelo EXIF
python timelapse_studio.py -i "D:\Fotos\GoPro_Viagem" --rename-source

# Execução direta com pasta personalizada e 30 FPS
python timelapse_studio.py -i "D:\Fotos\GoPro_Viagem" -fps 30 --run-all

# Executar modo de teste rápido
python timelapse_studio.py -i "C:\Imagens\Timelapse" --test
```

#### Parâmetros disponíveis:
- `-i`, `--input`, `--source`: Caminho da pasta onde estão as fotos JPG/JPEG.
- `-fps`, `--fps`: Taxa de quadros por segundo (ex: 15, 24, 30, 60).
- `--crop`: Posição do corte vertical (`center`, `top`, `bottom`).
- `--crf`: Fator de qualidade CRF (menor = maior qualidade, padrão 15).
- `--rename-source`: Renomeia as fotos de origem pelo EXIF (`%Y-%m-%d_%H-%M-%S_<original>.jpg`) e encerra.
- `--run-all`: Executa o pipeline completo (corte + renderização) sem abrir o menu.
- `--test`: Executa o teste rápido com amostragem reduzida e encerra.


