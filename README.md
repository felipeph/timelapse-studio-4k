# Timelapse Studio 4K UHD 🎥⚡

Automação em Python para processamento de fotos e renderização de timelapses em **4K UHD (3840x2160)** com suporte a aceleração por hardware (GPU: NVIDIA NVENC, AMD AMF, Intel QSV) e CPU multicore.

---

## 🚀 Funcionalidades

- **Multicâmeras**: Compatível com GoPro, Canon, Nikon, Sony e qualquer câmera (busca automática em subpastas `DCIM` ou na raiz).
- **Processamento 4K Paralelo**: Redimensionamento e crop inteligente (Centro, Topo, Base) utilizando todos os núcleos da CPU via `concurrent.futures`.
- **Renderização Rápida**: Detecção automática de aceleração por GPU (NVENC / AMF / QSV) com fallback transparente para CPU (`libx264`/`libx265`).
- **Menu Interativo CLI**:
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

Execute o script principal:

```bash
python timelapse_studio.py
```

Siga as opções do menu interativo no terminal.
