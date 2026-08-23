# Timelapse Studio 4K UHD 🎥⚡

Automação em Python para processamento de fotos e renderização de timelapses em **4K UHD (3840x2160)** com suporte a aceleração por hardware (GPU: NVIDIA NVENC, AMD AMF, Intel QSV) e CPU multicore.

---

## 🚀 Funcionalidades

- **Multicâmeras**: Compatível com GoPro, Canon, Nikon, Sony e qualquer câmera (busca automática em subpastas `DCIM` ou na raiz).
- **Pasta de Origem Personalizada**: Suporte para definir e alterar o diretório onde estão as fotos (com suporte a drag & drop no terminal do Windows).
- **Processamento 4K Paralelo**: Redimensionamento e crop inteligente (Centro, Topo, Base) utilizando todos os núcleos da CPU via `concurrent.futures`.
- **Renderização Rápida**: Detecção automática de aceleração por GPU (NVENC / AMF / QSV) com fallback transparente para CPU (`libx264`/`libx265`).
- **Menu Interativo CLI**:
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

Siga as opções do menu interativo no terminal. Você pode pressionar `[O]` a qualquer momento para definir ou alterar a pasta de origem das fotos (arrastando a pasta para a janela do terminal).

### 2. Linha de Comando (Modo Direto / Automação)

Você também pode passar argumentos diretamente via linha de comando:

```bash
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
- `--run-all`: Executa o pipeline completo (corte + renderização) sem abrir o menu.
- `--test`: Executa o teste rápido com amostragem reduzida e encerra.

