# 20260721 Repository Census

This document catalogues observed scaffolds, incomplete implementations, dangling code, and structurally disconnected elements within the repository.

## 1. Trash / Dangling Code
**Location:** `backend/app/runtimes/internetsearch/`
**Description:** This module contains complete internet search runtime implementations (`ddgs_runtime.py`, `searxng_runtime.py`, `tavily_runtime.py`, `base.py`). However, codebase inspection reveals that these files are completely disconnected from the rest of the application. No core routing or conversation engine logic imports them. They only reference themselves and have isolated unit tests. They provide no real usefulness to the working system in their current state.

## 2. Scaffold (Empty Boundary)
**Location:** `backend/app/extensions/mcp/`
**Description:** An empty directory that serves as a boundary scaffold for a future Model Context Protocol (MCP) integration. It currently lacks any operational implementation or supporting files.

## 3. Scaffold (Empty Boundary)
**Location:** `backend/app/extensions/skills/`
**Description:** An empty directory that serves as a boundary scaffold for agent skills. Like the MCP directory, it contains no code, schema, or functional implementation.

## 4. Incomplete Implementation
**Location:** `backend/app/runtimes/stt/onnx_whisper_runtime.py`
**Description:** The STT runtime explicitly contains a tracked, intentional `NotImplementedError` for the Qualcomm QNN execution provider (`ONNX_WHISPER_QNN_NOT_WIRED_REASON`). The code structure is present to detect QNN, but the execution path remains an incomplete implementation compared to the other functional acceleration paths (e.g., CUDA or DirectML for other components).
