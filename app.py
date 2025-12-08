import gradio as gr
import os
from rpa_agent import Recorder, LLMClient, CodeRunner

# Global instances/variables
recorder = Recorder()
runner = CodeRunner()

def run_recorder(url, mock_mode=False):
    """
    Launches the recorder and returns the raw code.
    """
    if mock_mode:
        # Fake code for testing in headless environments
        return """from playwright.sync_api import sync_playwright
def run(playwright):
    browser = playwright.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto('https://example.com')
    page.get_by_role("button", name="More information").click()
    browser.close()

with sync_playwright() as playwright:
    run(playwright)"""
    
    recorder.start_recording(url)
    return recorder.get_recorded_code()

def refine_code(api_key, base_url, model_name, task_desc, raw_code):
    if not api_key or not base_url:
        return "Please provide API Key and Base URL. / 请提供 API Key 和 Base URL。"
    
    llm = LLMClient(api_key, base_url, model_name)
    refined = llm.refine_code(task_desc, raw_code)
    return refined

def run_script(code):
    stdout, stderr, success = runner.run_code(code)
    output = f"--- STDOUT ---\n{stdout}\n\n--- STDERR ---\n{stderr}"
    if success:
        return output, gr.update(visible=False)
    else:
        return output, gr.update(visible=True) # Show fix button

def fix_script(api_key, base_url, model_name, code, console_output):
    if not api_key or not base_url:
        return "Please provide API Key and Base URL."
    
    # Extract error message from console output (simplistic approach)
    error_part = console_output.split("--- STDERR ---")[-1]
    
    llm = LLMClient(api_key, base_url, model_name)
    fixed_code = llm.fix_code(code, error_part)
    return fixed_code

with gr.Blocks(title="AI Playwright RPA Agent") as demo:
    gr.Markdown("# AI Playwright RPA Agent / AI 网页自动化助手")
    
    with gr.Row():
        with gr.Column():
            api_key = gr.Textbox(label="OpenAI API Key", type="password")
            base_url = gr.Textbox(label="Base URL", value="https://api.openai.com/v1")
            model_name = gr.Textbox(label="Model Name / 模型名称", value="gpt-4o")
    
    with gr.Row():
        task_desc = gr.Textbox(label="Task Description / 任务描述", placeholder="e.g., Login to X and download the report. / 例如：登录某网站并下载报表。")
        start_url = gr.Textbox(label="Start URL / 起始链接", placeholder="https://www.google.com")
    
    with gr.Row():
        # Hidden checkbox for testing in headless environments
        mock_mode = gr.Checkbox(label="Mock Mode (For Headless Testing)", visible=False, value=False)
        record_btn = gr.Button("Step 1: Start Recording / 开始录制", variant="primary")
    
    with gr.Row():
        raw_code_area = gr.Code(label="Raw Recorded Code / 录制的原始代码", language="python", lines=10)
    
    with gr.Row():
        refine_btn = gr.Button("Step 2: Refine with AI / AI 优化代码", variant="secondary")
    
    with gr.Row():
        refined_code_area = gr.Code(label="Refined Code / 优化后的代码", language="python", lines=15, interactive=True)
    
    with gr.Row():
        run_btn = gr.Button("Step 3: Run Code / 运行代码", variant="primary")
    
    with gr.Row():
        console_output = gr.Textbox(label="Console Output / 控制台输出", lines=10)
    
    with gr.Row():
        fix_btn = gr.Button("Fix Code with AI / 使用 AI 修复报错", visible=False, variant="stop")

    # Event Wiring
    record_btn.click(
        fn=run_recorder,
        inputs=[start_url, mock_mode],
        outputs=[raw_code_area]
    )
    
    refine_btn.click(
        fn=refine_code,
        inputs=[api_key, base_url, model_name, task_desc, raw_code_area],
        outputs=[refined_code_area]
    )
    
    run_btn.click(
        fn=run_script,
        inputs=[refined_code_area],
        outputs=[console_output, fix_btn]
    )
    
    fix_btn.click(
        fn=fix_script,
        inputs=[api_key, base_url, model_name, refined_code_area, console_output],
        outputs=[refined_code_area]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
