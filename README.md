# DebateRAG

DebateRAG is a FastAPI + Vue demo that visualizes a multi-agent debate pipeline for ambiguity detection in RAG. Users provide documents and a query, agents debate across retrieved evidence, an ambiguity solver highlights conflicting interpretations, and a synthesizer returns a final response. The UI streams steps in real time over WebSockets and animates the agents as they speak.

## Inspiration and Contributions
This project is inspired by the MaDAM-RAG paper ([arXiv:2504.13079](https://arxiv.org/abs/2504.13079)). While trying to reproduce the paper, I ran into two practical issues:
1) The base model's prior knowledge influenced results beyond the provided documents.
2) Individual agents produced ambiguous intermediate answers, which led to incorrect aggregation.

I addressed these by tightening the prompts to keep agents grounded in the documents and by changing the architecture from a pure aggregator to an explicit **Ambiguity Solver** stage that surfaces conflicting interpretations and guides clarification before final synthesis.

## Features
- Multi-agent debate pipeline with ambiguity detection and synthesis
- WebSocket streaming of intermediate steps
- Visual agent scene and live pipeline stage tracker
- Simple local demo with in-memory vector store

## Requirements
- Python 3.13+
- An OpenAI API key

## Setup

1) Install dependencies (uv is recommended):
```bash
uv sync
```

Or with pip:
```bash
pip install -e .
```

2) Set your API key:
```bash
export OPENAI_API_KEY=your_key_here
```

3) Start the server:
```bash
uvicorn app:app --reload
```

4) Open the UI:
```
http://127.0.0.1:8000/
```

## Usage

- Add up to 4 documents in the input panel.
- Enter a question.
- Choose 1-4 debate rounds.
- Click **Run Debate** to stream the process.

## WebSocket API

The frontend connects to `ws://127.0.0.1:8000/ws/debate` and sends a JSON payload on open:
```json
{
  "documents": ["Doc 1", "Doc 2"],
  "query": "What year was Michael Jordan born?",
  "rounds": 2,
  "top_k": 6
}
```


## Project Structure
- `app.py`: FastAPI server (REST + WebSocket)
- `debate_pipeline.py`: debate/ambiguity pipeline
- `web/`: Vue UI (index, styles, app script)


## Screenshots / Demo

![DebateRAG screenshot](https://github.com/lolove/DebateRAG/blob/main/screenshot.png)
