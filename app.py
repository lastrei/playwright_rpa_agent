"""
Gradio UI for Playwright RPA Agent.
Provides an interactive interface for recording, refining, and executing RPA tasks.
"""
import gradio as gr
import json
import os

from rpa_agent import Recorder, LLMClient, CodeRunner
from config import get_config_manager, get_config, DEFAULT_PROVIDERS
from logger import get_logger

# Initialize globals
logger = get_logger("app")
config_manager = get_config_manager()
config = get_config()

recorder = Recorder()
runner = CodeRunner()

def get_provider_choices():
    """Get list of available providers for dropdown."""
    return list(DEFAULT_PROVIDERS.keys())

def on_provider_change(provider_name):
    """Update API fields when provider changes."""
    try:
        current_config = get_config()
        current_config.switch_provider(provider_name)
        provider = current_config.get_active_provider()
        
        if provider:
            api_key = provider.api_key or ""
            base_url = provider.base_url or DEFAULT_PROVIDERS.get(provider_name, {}).get("base_url", "")
            model_name = provider.model_name or DEFAULT_PROVIDERS.get(provider_name, {}).get("default_model", "")
            return api_key, base_url, model_name
        
        # Fallback to defaults
        defaults = DEFAULT_PROVIDERS.get(provider_name, {})
        return "", defaults.get("base_url", ""), defaults.get("default_model", "")
    except Exception as e:
        logger.error(f"Error switching provider: {e}")
        return "", "", ""

def save_current_config(provider_name, api_key, base_url, model_name):
    """Save current configuration to file."""
    try:
        current_config = get_config()
        current_config.switch_provider(provider_name)
        current_config.set_provider(provider_name, api_key, base_url, model_name)
        if config_manager.save(current_config):
            return f"✅ Configuration saved for: {provider_name}"
        return "❌ Failed to save configuration"
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return f"❌ Error: {e}"

def run_recorder_wrapper(url, mock_mode=False):
    """Wrapper for recorder."""
    if mock_mode:
        return """from playwright.sync_api import sync_playwright

def run(playwright):
    browser = playwright.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto('https://example.com')
    page.get_by_role("button", name="More information").click()
    browser.close()

with sync_playwright() as playwright:
    run(playwright)"""
    
    if recorder.start_recording(url):
        return recorder.get_recorded_code()
    return "# Recording failed or cancelled"

def refine_code_wrapper(api_key, base_url, model_name, task_desc, raw_code):
    """Wrapper for code refinement."""
    if not api_key:
        return "# Error: Please provide API Key"
    if not base_url:
        return "# Error: Please provide Base URL"
    
    try:
        llm = LLMClient(api_key, base_url, model_name)
        return llm.refine_code(task_desc, raw_code)
    except Exception as e:
        logger.error(f"Error refining code: {e}")
        return f"# Error: {e}"

def run_script_wrapper(code):
    """Wrapper for running script with validation."""
    if not code or code.startswith("# Error"):
        return "No valid code to run", gr.update(visible=False), gr.update(visible=False)
    
    # First validate
    is_valid, issues = runner.validate_code(code)
    
    if not is_valid:
        issues_text = "\n".join(f"- {i}" for i in issues)
        return (
            f"⚠️ Validation Failed:\n{issues_text}", 
            gr.update(visible=True),
            gr.update(visible=False)
        )

    # Run if valid
    stdout, stderr, success = runner.run_code(code)
    output = f"--- STDOUT ---\n{stdout}\n\n--- STDERR ---\n{stderr}"
    
    if success:
        return f"✅ Success!\n{output}", gr.update(visible=False), gr.update(visible=False)
    else:
        return f"❌ Error:\n{output}", gr.update(visible=True), gr.update(visible=False)

def analyze_error_wrapper(api_key, base_url, model_name, code, console_output):
    """Analyze error and provide suggestions."""
    if not api_key:
        return "Missing API Key", gr.update(visible=False)

    validation_issues = []
    if "Validation Failed" in console_output:
        lines = console_output.split("\n")
        validation_issues = [l.strip("- ") for l in lines if l.startswith("- ")]
        error_part = "Code Validation Failed"
    else:
        error_part = console_output.split("--- STDERR ---")[-1] if "--- STDERR ---" in console_output else console_output

    try:
        llm = LLMClient(api_key, base_url, model_name)
        analysis = llm.analyze_error(code, error_part, validation_issues)
        return analysis, gr.update(visible=True)
    except Exception as e:
        logger.error(f"Error analyzing: {e}")
        return f"Error: {e}", gr.update(visible=False)

def fix_code_wrapper(api_key, base_url, model_name, code, analysis):
    """Fix code based on analysis."""
    try:
        llm = LLMClient(api_key, base_url, model_name)
        return llm.fix_code(code, f"Analysis:\n{analysis}")
    except Exception as e:
        logger.error(f"Error fixing code: {e}")
        return f"# Error: {e}"


# --- UI Layout ---

with gr.Blocks(title="AI Playwright RPA Agent", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🤖 AI Playwright RPA Agent")
    
    with gr.Accordion("⚙️ Configuration / 设置", open=True):
        with gr.Row():
            provider_dropdown = gr.Dropdown(
                choices=get_provider_choices(),
                value=config.active_provider,
                label="LLM Provider",
                interactive=True
            )
            save_config_btn = gr.Button("💾 Save Config", variant="secondary")
            
        with gr.Row():
            active_provider = config.get_active_provider()
            default_base_url = DEFAULT_PROVIDERS.get(config.active_provider, {}).get("base_url", "")
            default_model = DEFAULT_PROVIDERS.get(config.active_provider, {}).get("default_model", "")
            
            api_key_input = gr.Textbox(
                label="API Key", 
                type="password",
                value=active_provider.api_key if active_provider and active_provider.api_key else "",
                placeholder="Enter your API key"
            )
            base_url_input = gr.Textbox(
                label="Base URL", 
                value=active_provider.base_url if active_provider and active_provider.base_url else default_base_url
            )
            model_name_input = gr.Textbox(
                label="Model Name", 
                value=active_provider.model_name if active_provider and active_provider.model_name else default_model
            )
            
        config_status = gr.Markdown("")

    with gr.Tabs():
        with gr.TabItem("🛠️ Workspace"):
            with gr.Row():
                task_desc = gr.Textbox(
                    label="Task Description / 任务描述", 
                    placeholder="e.g., Login to Gmail and search for 'Invoice'",
                    lines=2
                )
                start_url = gr.Textbox(
                    label="Start URL / 起始链接", 
                    placeholder="https://www.google.com"
                )
            
            with gr.Row():
                mock_mode = gr.Checkbox(label="Mock Mode (Testing)", visible=False, value=False)
                record_btn = gr.Button("🔴 Step 1: Start Recording", variant="primary")
            
            with gr.Row():
                with gr.Column():
                    raw_code_area = gr.Code(
                        label="Raw Recorded Code", 
                        language="python", 
                        lines=12
                    )
                    refine_btn = gr.Button("✨ Step 2: Refine with AI", variant="secondary")
                
                with gr.Column():
                    refined_code_area = gr.Code(
                        label="Refined Code (Editable)", 
                        language="python", 
                        lines=12, 
                        interactive=True
                    )
                    run_btn = gr.Button("▶️ Step 3: Validate & Run", variant="primary")

        with gr.TabItem("📊 Execution & Analysis"):
            console_output = gr.Textbox(label="Console Output", lines=10)
            
            with gr.Row():
                analyze_btn = gr.Button("🔍 Analyze Error", visible=False, variant="secondary")
                fix_btn = gr.Button("🔧 Apply Fix", visible=False, variant="stop")
            
            analysis_output = gr.Markdown(label="Analysis")

    # --- Event Wiring ---
    
    provider_dropdown.change(
        fn=on_provider_change,
        inputs=[provider_dropdown],
        outputs=[api_key_input, base_url_input, model_name_input]
    )
    
    save_config_btn.click(
        fn=save_current_config,
        inputs=[provider_dropdown, api_key_input, base_url_input, model_name_input],
        outputs=[config_status]
    )

    record_btn.click(
        fn=run_recorder_wrapper,
        inputs=[start_url, mock_mode],
        outputs=[raw_code_area]
    )
    
    refine_btn.click(
        fn=refine_code_wrapper,
        inputs=[api_key_input, base_url_input, model_name_input, task_desc, raw_code_area],
        outputs=[refined_code_area]
    )
    
    run_btn.click(
        fn=run_script_wrapper,
        inputs=[refined_code_area],
        outputs=[console_output, analyze_btn, fix_btn]
    )
    
    analyze_btn.click(
        fn=analyze_error_wrapper,
        inputs=[api_key_input, base_url_input, model_name_input, refined_code_area, console_output],
        outputs=[analysis_output, fix_btn]
    )
    
    fix_btn.click(
        fn=fix_code_wrapper,
        inputs=[api_key_input, base_url_input, model_name_input, refined_code_area, analysis_output],
        outputs=[refined_code_area]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
