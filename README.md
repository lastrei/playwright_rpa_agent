# AI-Enhanced Playwright RPA Agent

This tool allows you to record web interactions using Playwright and then uses an LLM (like GPT-4) to refine the recorded code into a robust, reusable Python script.

## Features

- **Interactive Recording**: Uses `playwright codegen` to record your browser actions.
- **AI Refinement**: Converts raw selectors and clicks into meaningful logical steps (e.g., "Login" or "Extract Price") based on your natural language description.
- **Auto-Fix**: If the generated code fails to run, the AI can analyze the error log and fix the code automatically.
- **Multilingual UI**: Supports English and Chinese.

## Prerequisites

1. Python 3.8+
2. Valid OpenAI API Key (or compatible provider).

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Install Playwright browsers:
   ```bash
   playwright install
   ```

## Usage

1. Run the Gradio app:
   ```bash
   python app.py
   ```
2. Open your browser at `http://localhost:7860`.
3. **Configure**: Enter your OpenAI API Key.
4. **Step 1: Record**:
   - Enter a task description (e.g., "Go to Google, search for Python, and print the first result").
   - Click "Start Recording". A browser window will open.
   - Perform the actions. Close the browser when done.
5. **Step 2: Refine**:
   - Click "Refine with AI". The raw code will be transformed into a clean script.
6. **Step 3: Run**:
   - Click "Run Code" to test the script immediately.
   - If it fails, use the "Fix with AI" button.

## Customization

- **Model**: You can change the model name in the UI (e.g., `gpt-3.5-turbo`, `gpt-4`).
- **Base URL**: If you use a proxy or a different provider (like Azure or a local LLM), update the Base URL.
