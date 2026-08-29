# Timelapse Studio 4K UHD 🎥⚡

Automação em Python para processamento de fotos e renderização de timelapses em **4K UHD (3840x2160)** com suporte a aceleração por hardware (GPU: NVIDIA NVENC, AMD AMF, Intel QSV) e CPU multicore.

---

## 🚀 Funcionalidades

- **Configurações Persistentes em JSON (`config.json`)**: Preferências salvas automaticamente e ignoradas pelo Git. Na primeira execução sem o arquivo, um assistente interativo (wizard) ajuda o usuário a configurar seus parâmetros padrão.
- **Multicâmeras**: Compatível com GoPro, Canon, Nikon, Sony e qualquer câmera (busca automática em subpastas `DCIM` ou na raiz).
- **Pasta de Origem Personalizada**: Suporte para definir e alterar o diretório onde estão as fotos (com suporte a drag & drop no terminal do Windows).
- **Saída Unificada na Origem**: A pasta de fotos cortadas (`fotos_cortadas_4k`) e os arquivos de vídeo gerados (`timelapse_*.mp4`) são salvos diretamente no mesmo local da pasta de origem das fotos.
- **Organização e Renomeação por EXIF**: Padronização dos nomes das fotos para `%Y-%m-%d_%H-%M-%S_<nome_original>.jpg` com base na data/hora do cabeçalho EXIF.
- **Processamento 4K Paralelo com Preservação EXIF**: Redimensionamento e crop inteligente (Centro, Topo, Base) utilizando todos os núcleos da CPU via `concurrent.futures`, mantendo os dados EXIF no arquivo recortado com o sufixo `_crop4k.jpg`.
- **Nomenclatura Dinâmica de Vídeos**: Arquivo de vídeo nomeado automaticamente com base no intervalo cronológico das capturas (`timelapse_YYYY-MM-DD_HH-MM---HH-MM.mp4`).
- **Injeção de Metadados nos Vídeos**: Tags de contêiner MP4 (`creation_time`, `date`, `title`, `comment`) preenchidas automaticamente com a data e hora do início das fotos.
- **Renderização Rápida**: Detecção automática de aceleração por GPU (NVENC / AMF / QSV) com fallback transparente para CPU (`libx264`/`libx265`).
- **Controle Preciso de Velocidade (Frames por Imagem / FPI)**: Permite escolher quantos frames cada foto ficará visível no vídeo final mantendo a taxa de quadros (ex: vídeo em 60 FPS com 60 frames por foto para ter 1 segundo de exibição por foto, ou 2 frames por foto para desacelerar o timelapse sem perder fluidez).
- **Menu Interativo CLI**:
  - Organizar/renomear fotos de origem por EXIF (`[R]`).
  - Seleção e troca da pasta de origem das fotos (`[O]`).
  - Teste rápido de renderização (amostra de fotos).
  - Ajuste dinâmico de taxa de quadros (FPS: 24, 30, 60, etc.) (`[F]`).
  - Ajuste de frames por imagem / tempo de exibição por foto (`[P]`).
  - Configuração de modo de enquadramento (Crop) (`[C]`).
  - Menu de Configurações Avançadas e Persistência em JSON (`[5]`).
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

## ⚙️ Configurações & Arquivo `config.json`

O Timelapse Studio suporta carregamento automático de opções através de um arquivo `config.json`.

### Assistente de Primeira Execução (Wizard)
Na primeira vez que você executar o script sem um `config.json`, ele iniciará automaticamente um assistente interativo no terminal perguntando suas preferências (pressionando `Enter` aceita o valor padrão sugerido).

O arquivo gerado é mantido localmente e já está no `.gitignore` para não ser enviado ao repositório.

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
  "test_sample_size": 120
}
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
- Pressione `[F]` para alterar a taxa de quadros (FPS) do vídeo de saída.
- Pressione `[P]` para ajustar quantos frames cada imagem/foto vai durar no vídeo (ex: 60 frames/foto para durar 1 segundo por foto a 60 FPS).
- Pressione `[5]` para salvar as configurações atuais no `config.json` ou restaurar padrões de fábrica.
- Pressione `[1]` para processar os cortes 4K e `[2]` para gerar o vídeo final com metadados e nome cronológico.

### 2. Linha de Comando (Modo Direto / Automação)

Você também pode passar argumentos diretamente via linha de comando:

```bash
# Executar usando um arquivo de configuração customizado
python timelapse_studio.py -c meu_perfil.json

# Renomear fotos da pasta de origem pelo EXIF
python timelapse_studio.py -i "D:\Fotos\GoPro_Viagem" --rename-source

# Execução direta com pasta personalizada, 60 FPS e 60 frames por imagem (1 foto por segundo)
python timelapse_studio.py -i "D:\Fotos\GoPro_Viagem" -fps 60 -fpi 60 --run-all

# Execução direta com 60 FPS e 2 frames por imagem
python timelapse_studio.py -i "D:\Fotos\GoPro_Viagem" -fps 60 -fpi 2 --run-all

# Executar modo de teste rápido
python timelapse_studio.py -i "C:\Imagens\Timelapse" --test
```

#### Parâmetros disponíveis:
- `-c`, `--config`: Caminho para o arquivo JSON de configuração (padrão: `config.json`).
- `-i`, `--input`, `--source`: Caminho da pasta onde estão as fotos JPG/JPEG.
- `-fps`, `--fps`: Taxa de quadros por segundo (ex: 15, 24, 30, 60).
- `-fpi`, `--fpi`, `--frames-per-image`: Número de frames exibidos por cada foto no vídeo (ex: 60 para manter 1 foto/segundo em 60 FPS, padrão: 1).
- `--crop`: Posição do corte vertical (`center`, `top`, `bottom`).
- `--crf`: Fator de qualidade CRF (menor = maior qualidade, padrão 15).
- `--no-wizard`: Não executa o assistente inicial caso o `config.json` não exista.
- `--rename-source`: Renomeia as fotos de origem pelo EXIF (`%Y-%m-%d_%H-%M-%S_<original>.jpg`) e encerra.
- `--run-all`: Executa o pipeline completo (corte + renderização) sem abrir o menu.
- `--test`: Executa o teste rápido com amostragem reduzida e encerra.
