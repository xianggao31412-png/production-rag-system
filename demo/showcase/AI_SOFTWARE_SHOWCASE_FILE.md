# AI Software Showcase File

> 这是一份**展示文档**。把它导入「企业知识助手平台」后,你可以对它提问,从而看到这个软件的全部
> 核心能力:导入文档 → 混合检索(关键词 + 语义)→ 重排序 → 带引用的回答 → 可观测仪表盘。
> 运行 `RUN_DEMO.bat` / `python run_demo.py`,或在仪表盘点击 **Run showcase demo**,会自动用
> 这份文件演示所有功能。

This document is meant to be ingested by the Enterprise Knowledge Assistant. Once
loaded, you can ask questions about it and watch the platform retrieve, rerank,
and answer with citations. The facts below are written as plain self-contained
sentences so the answers come back clean.

## Software purpose

This platform is a production-grade hybrid-retrieval RAG system that ingests your
documents and answers natural-language questions about them with grounded, cited
answers. It is a knowledge assistant that reads your files and tells you what they
say, with the source attached, rather than a code analyzer.

## What the platform can do

The Enterprise Knowledge Assistant ingests TXT, Markdown, CSV, and PDF files,
splits them into passages, and indexes them with both a BM25 keyword index and a
dense vector store. At query time it runs a six-stage pipeline (embed, vector
search, keyword search, fusion, rerank, generate) and returns an answer whose
every claim is backed by a numbered citation. It runs fully offline by default
and upgrades to a local Ollama model by changing environment variables.

## Core capabilities

The platform fuses BM25 keyword search with dense vector search for hybrid retrieval.
A reranking stage reorders candidates so the most relevant passages reach the answer.
Answers are grounded and carry inline numbered citations with a grounded-or-not flag.
Namespaces isolate separate document collections so they never mix together.
Security uses API-key authentication and per-client token-bucket rate limiting.
Logging is structured JSON with a request id traced across the whole pipeline.
Health and readiness probes make the service easy to run under orchestration.
A live operations dashboard lights up the retrieval pipeline with measured latencies.
An extractive fallback keeps answers flowing even when no language model is reachable.
Production backends like Ollama, ChromaDB, and a cross-encoder reranker are one setting away.

## Helios Robotics knowledge base

Helios Robotics is a robotics company founded in 2016 and headquartered in Toronto, Canada.
Helios Robotics employs 240 people across engineering, operations, and support.
The Helios One is the company's flagship autonomous mobile robot.
The Helios One battery lasts 8 hours on a single charge and carries a maximum payload of 5 kilograms.
The Helios One is priced at 12,000 US dollars and ships with a 24-month hardware warranty.
Helios Robotics support is available from 9:00 AM to 6:00 PM Eastern Time, Monday through Friday.
Priority customers are guaranteed a first response within 4 business hours under the standard SLA.
All customer data is encrypted at rest using AES-256 and in transit using TLS 1.3.
Helios Robotics completed its SOC 2 Type II audit and retains customer telemetry for 90 days before deletion.

## What this demonstrates to HR and clients

Applied RAG and search engineering: hybrid retrieval, rank fusion, and reranking rather than a thin wrapper.
Production thinking: authentication, rate limiting, health and readiness probes, structured request-traced logging.
Observability and UX: a live dashboard that makes the system's internal behaviour visible and explainable.
Reliability: answers are assembled only from your documents and always cited, with graceful degradation when the LLM is down.
Deployability: a one-click launcher, Docker packaging, offline operation, and a config switch to local LLMs.
Engineering rigor: a comprehensive test suite and an iterative build log documenting real bugs found and fixed.

## How to run

Double-click START_SOFTWARE.bat to set everything up, start the server, and open the dashboard.
Double-click RUN_DEMO.bat, or run python run_demo.py, for a narrated command-line tour.
In the dashboard, click Run showcase demo to ingest this file and run the demo questions automatically.
