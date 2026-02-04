from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_openai import OpenAIEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

DEFAULT_MODEL = "gpt-5-nano-2025-08-07"
EMBEDDING_MODEL = "text-embedding-3-large"


@dataclass
class DebateStep:
    stage: str
    speaker: str
    message: str
    round: int | None = None
    doc_id: int | None = None


def _run_agent(model: Any, query: str, system_prompt: str) -> str:
    agent = create_agent(model, tools=[], system_prompt=system_prompt)
    last_content = ""
    for event in agent.stream(
        {"messages": [{"role": "user", "content": query}]},
        stream_mode="values",
    ):
        message = event["messages"][-1]
        if message.content:
            last_content = message.content
    return (last_content or "").strip()


def _compact(text: str, limit: int = 200) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def stream_debate(
    documents: list[str],
    query: str,
    model_name: str = DEFAULT_MODEL,
    top_k: int = 6,
    rounds: int = 2,
) -> Any:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set in the environment.")

    cleaned_docs = [doc.strip() for doc in documents if doc.strip()]
    if not cleaned_docs:
        raise ValueError("At least one non-empty document is required.")

    model = init_chat_model(model_name, temperature=0)
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    vector_store = InMemoryVectorStore(embeddings)

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        add_start_index=True,
    )
    metadatas = [
        {"doc_id": index + 1, "source": f"user_doc_{index + 1}"}
        for index in range(len(cleaned_docs))
    ]
    all_splits = text_splitter.create_documents(cleaned_docs, metadatas=metadatas)

    step = DebateStep(
        stage="setup",
        speaker="System",
        message=(
            f"Received {len(cleaned_docs)} documents. Split into {len(all_splits)} chunks."
        ),
    )
    yield {"event": "step", "data": step.__dict__}

    step = DebateStep(
        stage="indexing",
        speaker="Indexer",
        message="Embedding documents for retrieval...",
    )
    yield {"event": "step", "data": step.__dict__}

    t_embed_start = time.perf_counter()
    vector_store.add_documents(documents=all_splits)
    t_embed_end = time.perf_counter()

    retrieved_docs = vector_store.similarity_search(
        query, k=min(top_k, len(all_splits))
    )

    step = DebateStep(
        stage="setup",
        speaker="System",
        message=(
            f"Retrieved {len(retrieved_docs)} chunks for the query."
        ),
    )
    yield {"event": "step", "data": step.__dict__}

    retrieval_lines = []
    for idx, doc in enumerate(retrieved_docs, start=1):
        doc_id = doc.metadata.get("doc_id")
        excerpt = _compact(doc.page_content)
        retrieval_lines.append(f"[{idx}] Doc {doc_id}: {excerpt}")
    step = DebateStep(
        stage="retrieval",
        speaker="Retriever",
        message="\n".join(retrieval_lines) if retrieval_lines else "No chunks retrieved.",
    )
    yield {"event": "step", "data": step.__dict__}

    intermediate_results: list[str] = []
    for idx, doc in enumerate(retrieved_docs, start=1):
        prompt = (
            "You are an agent reading a single document to answer the user question.\n\n"
            "Question: {query}\n"
            "Document: {doc}\n"
            "Only use the document. If the document does not contain an answer, say so. "
            "Provide a short answer and a brief explanation.\n"
            "Format: Answer: <answer>. Explanation: <why>."
        )
        response = _run_agent(
            model,
            query,
            prompt.format(query=query, doc=doc.page_content),
        )
        intermediate_results.append(response)
        step = DebateStep(
            stage="evidence",
            speaker=f"Doc Agent {idx}",
            message=response,
            round=0,
            doc_id=doc.metadata.get("doc_id"),
        )
        yield {"event": "step", "data": step.__dict__}

    ambiguity_prompt = (
        "You detect ambiguity versus factual conflict in answers.\n\n"
        "Question: {query}\n"
        "Responses: {responses}\n"
        "If answers conflict, suggest clarification questions or guidance to disambiguate. "
        "If the question is ambiguous, list the plausible interpretations.\n"
        "Format: Guidance: <guidance>. Questions: <questions>."
    )
    ambiguity_guidance = _run_agent(
        model,
        query,
        ambiguity_prompt.format(query=query, responses="\n".join(intermediate_results)),
    )
    step = DebateStep(
        stage="ambiguity",
        speaker="Ambiguity Solver",
        message=ambiguity_guidance,
        round=0,
    )
    yield {"event": "step", "data": step.__dict__}

    for round_idx in range(1, rounds + 1):
        history_results = intermediate_results
        intermediate_results = []

        for idx, doc in enumerate(retrieved_docs, start=1):
            debate_prompt = (
                "You are an agent refining your answer using peer responses and ambiguity guidance.\n\n"
                "Question: {query}\n"
                "Document: {doc}\n"
                "Peer responses: {responses}\n"
                "Ambiguity guidance: {guidance}\n"
                "Only use the document and the provided responses. Clarify what you are referring to.\n"
                "Format: Answer: <answer>. Explanation: <why>."
            )
            response = _run_agent(
                model,
                query,
                debate_prompt.format(
                    query=query,
                    doc=doc.page_content,
                    responses="\n".join(history_results),
                    guidance=ambiguity_guidance,
                ),
            )
            intermediate_results.append(response)
            step = DebateStep(
                stage="debate",
                speaker=f"Debater {idx}",
                message=response,
                round=round_idx,
                doc_id=doc.metadata.get("doc_id"),
            )
            yield {"event": "step", "data": step.__dict__}

        ambiguity_guidance = _run_agent(
            model,
            query,
            ambiguity_prompt.format(query=query, responses="\n".join(intermediate_results)),
        )
        step = DebateStep(
            stage="ambiguity",
            speaker="Ambiguity Solver",
            message=ambiguity_guidance,
            round=round_idx,
        )
        yield {"event": "step", "data": step.__dict__}

    summarizer_prompt = (
        "You synthesize a final answer based only on the provided responses.\n\n"
        "Question: {query}\n"
        "Responses: {responses}\n"
        "If answers disagree because the question is ambiguous, list all valid answers "
        "and ask the user to clarify.\n"
        "Format: Final Answer: <answer>."
    )
    final_answer = _run_agent(
        model,
        query,
        summarizer_prompt.format(query=query, responses="\n".join(intermediate_results)),
    )
    step = DebateStep(
        stage="synthesis",
        speaker="Synthesizer",
        message=final_answer,
        round=rounds,
    )
    yield {"event": "step", "data": step.__dict__}

    stats = {
        "documents": len(cleaned_docs),
        "chunks": len(all_splits),
        "retrieved": len(retrieved_docs),
        "model": model_name,
        "rounds": rounds,
        "embedding_seconds": round(t_embed_end - t_embed_start, 3),
    }

    yield {"event": "done", "final_answer": final_answer, "stats": stats, "query": query}


def run_debate(
    documents: list[str],
    query: str,
    model_name: str = DEFAULT_MODEL,
    top_k: int = 6,
    rounds: int = 2,
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    final_answer = ""
    stats: dict[str, Any] = {}

    for event in stream_debate(
        documents=documents,
        query=query,
        model_name=model_name,
        top_k=top_k,
        rounds=rounds,
    ):
        if event.get("event") == "step":
            steps.append(event["data"])
        elif event.get("event") == "done":
            final_answer = event["final_answer"]
            stats = event["stats"]

    return {
        "query": query,
        "steps": steps,
        "final_answer": final_answer,
        "stats": stats,
    }
