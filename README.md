# A.D.A - Pocket AI

A.D.A (Advanced Digital Assistant) is a localized, privacy-focused AI assistant built with PySide6 and powered by local large language models. It provides a comprehensive suite of tools including smart home control, web search, personal planning, and AI-curated news daily briefings.

## 🚀 Features

- **Dashboard**: A central hub showing weather (via Open-Meteo), upcoming calendar events, and app status.
- **AI Chat**: Interactive chat interface with local LLMs (via Ollama), featuring streaming responses and "thinking" tokens.
- **Daily Briefing**: AI-curated news summaries fetched from DuckDuckGo, categorizing top stories, technology, and science.
- **Home Automation**: Control TP-Link Kasa smart devices (lights, plugs) directly from the interface.
- **Web Agent**: A specialized interface for web-based tasks and browsing assistance.
- **Planner**: Manage your schedule with a local SQLite-backed calendar.
- **System Monitor**: Real-time CPU and Memory tracking integrated into the title bar.
- **TTS (Text-to-Speech)**: High-quality voice output using Piper TTS with streaming support.

## 🛠️ Prerequisites

- **Python**: 3.10 or higher.
- **Ollama**: Must be installed and running locally.
- **Hardware**: 
  - NVIDIA GPU (optional but recommended for the Router model).
  - ~8GB+ RAM for comfortable model execution.

## 📦 Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd pocket_ai
   ```

2. **Install dependencies**:
   ```bash
   pip install PySide6 qfluentwidgets requests duckduckgo-search python-kasa piper-tts sounddevice numpy torch transformers
   ```

3. **Model Setup**:
   - Install **Ollama** from [ollama.com](https://ollama.com).
   - Pull the responder model (default: `qwen3:1.7b`):
     ```bash
     ollama pull qwen3:1.7b
     ```
   - Ensure you have the fine-tuned Router model in the `./merged_model` directory (or update the path in `config.py`).

## ⚙️ Configuration

Main configuration is located in `config.py`. Key settings include:
- `RESPONDER_MODEL`: The Ollama model to use for chat.
- `OLLAMA_URL`: Local endpoint for Ollama (default: `http://localhost:11434/api`).
- `LOCAL_ROUTER_PATH`: Path to the fine-tuned FunctionGemma router.
- `ROUTER_KEYWORDS`: Keywords that trigger specialized routing.

## 🖥️ Usage

Run the application using the main entry point:

```bash
python main.py
```

### Key Controls:
- **Navigation**: Use the sidebar to switch between Dashboard, Chat, Planner, Briefing, Home Auto, and Web Agent.
- **Voice**: Toggle TTS in the Chat tab to hear responses.
- **Home Auto**: Click the "Refresh" icon to scan for Kasa devices on your local network.

## 🏗️ Architecture

A.D.A is built using a modern Python stack:
- **UI Framework**: [PySide6](https://doc.qt.io/qtforpython/) with [QFluentWidgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) for a sleek Windows 11 aesthetic.
- **AI Backend**: [Ollama](https://ollama.com/) for local LLM inference.
- **Routing**: [Transformers](https://huggingface.co/docs/transformers/) with a fine-tuned Gemma model for intent recognition.
- **Services**:
  - **Weather**: Open-Meteo API (No key required).
  - **News**: DuckDuckGo Search.
  - **Storage**: SQLite for local calendar and chat history.
  - **TTS**: Piper for localized, fast speech synthesis.

## 📄 License

[Insert License Info Here]
