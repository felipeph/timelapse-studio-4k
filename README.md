# Timelapse Studio 4K UHD 🎥⚡

Automação em Python para processamento de fotos e renderização de timelapses em **4K UHD (3840x2160)** com suporte a aceleração por hardware (GPU: NVIDIA NVENC, AMD AMF, Intel QSV) e CPU multicore.

---

## 🚀 Funcionalidades

- **Pipeline Completo em 4 Etapas Integradas**:
  1. **Etapa 1 - Organização e Renomeação por EXIF**: Padronização dos nomes das fotos originais para `%Y-%m-%d_%H-%M-%S_<original>.jpg` com base na data/hora do disparo.
  2. **Etapa 2 - Processamento e Corte 4K Paralelo**: Redimensionamento e crop inteligente (Centro, Topo, Base) em 16:9 via `PIL` multicore, preservando metadados EXIF.
  3. **Etapa 3 - Renderização de Vídeo 4K Ultra-rápida**: Detecção automática de aceleração GPU (NVENC/AMF/QSV) com fallback para CPU, injeção de metadados de vídeo e nomenclatura cronológica dinâmica (`timelapse_YYYY-MM-DD_HH-MM---HH-MM.mp4`).
  4. **Etapa 4 - Limpeza Automática Pós-Vídeo**: Remoção automática das fotos cortadas intermediárias após a geração do vídeo para economizar espaço em disco.
- **Execução com 1 Clique (`[ENTER]` Padrão)**: Ao abrir o script, basta pressionar **ENTER** para disparar todo o fluxo sequencial (Etapas 1 ➔ 2 ➔ 3 ➔ 4).
- **Interface Organizada em 2 Telas**:
  - **Tela 1**: Menu de Execução e Pipeline Sequencial.
  - **Tela 2 (`[7]`)**: Central de Configurações e Persistência no `config.json`.
- **Configurações Persistentes em JSON (`config.json`)**: Preferências salvas automaticamente e ignoradas pelo Git. Assistente interativo (wizard) na primeira execução.
- **Controle Preciso de Velocidade (Frames por Imagem / FPI)**: Permite escolher quantos frames cada foto durará no vídeo mantendo a taxa de quadros (ex: 60 FPS com 60 frames/foto para 1s por foto).

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
  "test_sample_size": 120,
  "auto_clean_crops": true
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
- **Pressione `[ENTER]` ou `[6]`**: Dispara o **Fluxo Completo** (Etapas 1 ➔ 2 ➔ 3 ➔ 4).
- `[1]`: Etapa 1 - Organizar e renomear fotos de origem por EXIF.
- `[2]`: Etapa 2 - Cortar e redimensionar fotos para 4K UHD.
- `[3]`: Etapa 3 - Gerar o vídeo timelapse 4K.
- `[4]`: Etapa 4 - Limpar/apagar a pasta de fotos cortadas intermediárias.
- `[5]`: Modo Teste Rápido (amostra de 120 fotos).
- `[7]`: ⚙️ Abrir a **Tela 2 de Configurações**.
- `[0]`: Sair.

#### Tela 2: Menu de Configurações (Opção `[7]`)
- Altere Pasta de Origem, FPS, Frames por Imagem (FPI), Modo de Corte, CRF, Resolução e Preset.
- Ative/Desative a Limpeza Automática pós-vídeo (`[9]`).
- Pressione `[S]` para salvar no `config.json` ou `[D]` para restaurar padrões de fábrica.

---

### 2. Linha de Comando (Modo Direto / Automação)

Você também pode passar argumentos diretamente via linha de comando:

```bash
# Executar usando um arquivo de configuração customizado
python timelapse_studio.py -c meu_perfil.json

# Executar o fluxo completo automatizado (Etapas 1 a 4)
python timelapse_studio.py -i "D:\Fotos\GoPro_Viagem" -fps 60 -fpi 60 --run-all

# Renomear fotos da pasta de origem pelo EXIF e sair
python timelapse_studio.py -i "D:\Fotos\GoPro_Viagem" --rename-source

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
- `--rename-source`: Renomeia as fotos de origem pelo EXIF e encerra.
- `--run-all`: Executa o pipeline completo (Etapas 1 a 4) sem abrir o menu.
- `--test`: Executa o teste rápido com amostragem reduzida e encerra.
