# RAG vs. Contradictions: making models admit “there are multiple answers”

I’ve been working on a small project around a surprisingly common RAG failure mode:

**What happens when the retrieved sources contain contradictions or when the question legitimately has multiple correct answers?**

While reading MaDAM-RAG paper ([arXiv:2504.13079](https://arxiv.org/abs/2504.13079)), I got inspired by their point about **contradictory evidence** in retrieval. In real usage, this can be dangerous in a quiet way:
a RAG system may return **one** confident answer, and the user may never notice there were **other valid options** (or that the sources disagree).

So I tested it.

### What I observed with vanilla RAG + frontier LLMs

Even when I explicitly asked for “all valid answers,” the model often **collapsed to one** “most likely” answer.

### What I built: Debate-style RAG (inspired by the paper)

I reproduced the “agents debate” idea and ran experiments. Early on, I hit two big problems:

1. **Model priors leaked in** (agents used background knowledge beyond the provided documents).
2. **Messy intermediate answers** → incorrect aggregation (agents were vague, and the final step mixed signals).

After a lot of prompt iteration + orchestration tweaks, I got the architecture working reliably...but **it’s slow**, because debate needs multiple rounds (parallel helps, but round-trips still cost time).

### Plot twist

I took the *final* prompt that worked best in DebateRAG and used it as the **system prompt for a single agent**.

It worked **surprisingly well**: faster, and much better at:

* surfacing **multiple valid answers**
* flagging **disagreements**
* grounding claims in the retrieved snippets

![DebateRAG screenshot](https://github.com/lolove/DebateRAG/blob/main/screenshot.png)
