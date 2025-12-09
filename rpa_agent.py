"""
RPA Agent core module for Playwright automation.
Provides recording, LLM integration, code validation, and execution capabilities.
"""
import os
import subprocess
import tempfile
import time
from typing import Tuple, Optional, List
from openai import OpenAI

from config import get_config
from logger import get_logger

# Module logger
logger = get_logger("rpa_agent")


class CodeValidator:
    """Validates generated code before execution for security."""
    
    def __init__(self):
        self.config = get_config()
        self.logger = get_logger("validator")
    
    def validate(self, code: str) -> Tuple[bool, List[str]]:
        """
        Validate code for security issues.
        Returns (is_valid, list_of_issues).
        """
        issues = []
        
        if not self.config.enable_code_validation:
            return True, []
        
        # Check for blocked imports/calls
        for blocked in self.config.blocked_imports:
            if blocked in code:
                issues.append(f"Potentially dangerous code detected: '{blocked}'")
                self.logger.warning(f"Blocked pattern detected: {blocked}")
        
        # Check for basic syntax errors
        try:
            compile(code, '<string>', 'exec')
        except SyntaxError as e:
            issues.append(f"Syntax error at line {e.lineno}: {e.msg}")
            self.logger.error(f"Syntax error in code: {e}")
        
        is_valid = len(issues) == 0
        return is_valid, issues


class Recorder:
    """Handles Playwright codegen recording sessions."""
    
    def __init__(self):
        self.output_path = os.path.join(tempfile.gettempdir(), "playwright_recording_temp.py")
        self.config = get_config()
        self.logger = get_logger("recorder")

    def start_recording(self, url: str = None) -> bool:
        """
        Launches playwright codegen.
        Returns True if recording completed successfully.
        """
        cmd = ["playwright", "codegen", "-o", self.output_path]
        if url:
            cmd.append(url)
        
        self.logger.info(f"Starting recording session, output: {self.output_path}")
        if url:
            self.logger.info(f"Starting URL: {url}")
        
        try:
            subprocess.run(
                cmd, 
                check=True, 
                timeout=self.config.recording_timeout
            )
            self.logger.info("Recording session completed")
            return True
        except subprocess.TimeoutExpired:
            self.logger.error(f"Recording timed out after {self.config.recording_timeout}s")
            return False
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error during recording: {e}")
            return False
        except FileNotFoundError:
            self.logger.error("Playwright not found. Is it installed?")
            return False

    def get_recorded_code(self) -> str:
        """Reads the captured code from the temporary file."""
        if os.path.exists(self.output_path):
            with open(self.output_path, "r", encoding="utf-8") as f:
                code = f.read()
                self.logger.debug(f"Read {len(code)} bytes from recording file")
                return code
        self.logger.warning("No recording file found")
        return ""


class LLMClient:
    """Client for LLM API interactions with retry support."""
    
    def __init__(self, api_key: str = None, base_url: str = None, model_name: str = None):
        self.config = get_config()
        self.logger = get_logger("llm_client")
        
        # Use provided values or fall back to config
        provider = self.config.get_active_provider()
        self.api_key = api_key or (provider.api_key if provider else "")
        self.base_url = base_url or (provider.base_url if provider else "")
        self.model_name = model_name or (provider.model_name if provider else "")
        
        self.max_retries = self.config.llm_max_retries
        self.retry_delay = self.config.llm_retry_delay
        
        # Create client without proxy to avoid environment conflicts
        try:
            import httpx
            http_client = httpx.Client(timeout=60.0)
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                http_client=http_client
            )
        except Exception as e:
            self.logger.warning(f"Could not create custom http client: {e}, using default")
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        self.logger.info(f"LLMClient initialized: model={self.model_name}, base_url={self.base_url}")

    def _call_with_retry(self, messages: list) -> Optional[str]:
        """Make API call with retry logic."""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=0.0  # Strict mode - follow instructions exactly
                )
                return self._clean_output(response.choices[0].message.content)
            except Exception as e:
                last_error = e
                wait_time = self.retry_delay * (2 ** attempt)  # Exponential backoff
                self.logger.warning(f"API call failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    self.logger.info(f"Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
        
        self.logger.error(f"All {self.max_retries} API call attempts failed")
        raise last_error

    def refine_code(self, user_prompt: str, raw_code: str) -> str:
        """
        Sends the user prompt and raw code to the LLM to generate refined Playwright code.
        Uses template-based approach to preserve all original selectors.
        """
        system_prompt = """You are a Playwright code refiner. Your job is to take recorded code and make it production-ready.

## SELECTOR STABILIZATION RULES:

1. **CONVERT UNSTABLE SELECTORS TO STABLE ONES**:
   - If you see patterns like `.filter(has_text=re.compile(r"^$"))` - these are UNSTABLE
   - Convert them to stable CSS nth-child selectors or direct locator paths
   
   Example conversions:
   ```
   # UNSTABLE (recorded):
   page.get_by_role("link").filter(has_text=re.compile(r"^$")).nth(1).click()
   
   # STABLE (converted) - use CSS selector with nth-child:
   page.locator("section.feed-container a.note-item").nth(0).click()
   # OR use XPath:
   page.locator("xpath=//section[contains(@class,'feed')]//a[1]").click()
   ```

2. **PREFER THESE SELECTOR TYPES (in order of stability)**:
   - `page.locator("css=...")` - CSS selectors with classes/IDs
   - `page.locator("xpath=...")` - XPath for complex structures
   - `page.locator("[data-testid='...']")` - Test IDs if available
   - `page.locator("text=...")` - Exact text (if text is stable)

3. **AVOID THESE UNSTABLE PATTERNS**:
   - `.filter(has_text=re.compile(...))` - regex filters are fragile
   - `.get_by_role("link").nth(N)` without context - too generic
   - Selectors that depend on dynamic text content

4. **WHEN YOU CAN'T DETERMINE STABLE SELECTOR**:
   - Add a comment: `# TODO: Verify this selector on the actual page`
   - Keep the original selector but wrap in try/except

## UNDERSTANDING USER INTENT:

- If user says "wait for manual login" or "let user login manually":
  → SKIP the recorded login steps (phone input, verification code, login button)
  → Add `input("Please complete login manually, then press Enter...")` BEFORE the post-login actions
  → Keep only the non-login selectors (like clicking notes, browsing content)

- If user wants to "save login state" or mentions persistence:
  → Use `launch_persistent_context` to save COMPLETE browser profile (cookies, cache, IndexedDB, etc.)
  → This automatically persists login state across runs

## STANDARD PERSISTENT CONTEXT PATTERN (use this when persistence is mentioned):
```python
USER_DATA_DIR = "user_data"
os.makedirs(USER_DATA_DIR, exist_ok=True)

# Use persistent context - saves complete browser profile automatically
context = playwright.chromium.launch_persistent_context(
    USER_DATA_DIR,
    headless=False
)
page = context.pages[0] if context.pages else context.new_page()

# Check if login needed and prompt user
# Login is automatically saved to USER_DATA_DIR
```

## WHAT YOU MAY ADD:
- Comments explaining steps
- `print()` statements for progress
- `input()` for user pauses
- `try/except` blocks for error handling
- `page.wait_for_timeout(ms)` for stability
- `page.keyboard.press("Escape")` instead of element-specific press calls
- `os.makedirs("user_data", exist_ok=True)` for creating directories

## OUTPUT:
- Return ONLY valid Python code, no markdown
- Include all necessary imports"""

        user_message = f"""## User's Intent:
{user_prompt}

## ORIGINAL RECORDED CODE:
{raw_code}

## Instructions:
1. Understand the user's intent - if they want manual login, SKIP the login automation steps
2. Preserve selectors for the main workflow actions (like clicking notes, browsing)
3. Add user_data persistence if mentioned: save to "user_data/state.json"
4. Add comments and print() for progress
5. Keep the browser open at the end unless user says otherwise

Output the refined code now:"""

        self.logger.info("Refining code with LLM...")
        try:
            result = self._call_with_retry([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ])
            self.logger.info("Code refinement completed")
            return result
        except Exception as e:
            self.logger.error(f"Failed to refine code: {e}")
            return f"# Error calling LLM: {str(e)}"

    def fix_code(self, code: str, error_message: str) -> str:
        """
        Sends the broken code and error message to the LLM to fix it.
        """
        system_prompt = (
            "You are an expert Python debugger. "
            "Fix the following Playwright code based on the error message provided. "
            "Return ONLY the fixed python code, no markdown backticks."
        )
        
        user_message = (
            f"Code:\n{code}\n\n"
            f"Error Message:\n{error_message}\n\n"
            "Please fix the code."
        )

        self.logger.info("Fixing code with LLM...")
        try:
            result = self._call_with_retry([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ])
            self.logger.info("Code fix completed")
            return result
        except Exception as e:
            self.logger.error(f"Failed to fix code: {e}")
            return f"# Error calling LLM: {str(e)}"

    def analyze_error(self, code: str, error_message: str, validation_issues: List[str] = None) -> str:
        """
        Analyzes code errors and validation issues, providing suggestions.
        Returns a human-readable analysis with suggestions.
        """
        system_prompt = (
            "You are an expert Python and Playwright debugger. "
            "Analyze the following code issues and provide:\n"
            "1. A clear explanation of what went wrong\n"
            "2. Specific suggestions for fixing each issue\n"
            "3. Any potential security concerns if applicable\n"
            "Be concise but thorough. Format your response clearly."
        )
        
        issues_text = ""
        if validation_issues:
            issues_text = "Validation Issues:\n" + "\n".join(f"- {issue}" for issue in validation_issues) + "\n\n"
        
        user_message = (
            f"Code:\n```python\n{code}\n```\n\n"
            f"{issues_text}"
            f"Runtime Error (if any):\n{error_message}\n\n"
            "Please analyze and provide suggestions."
        )

        self.logger.info("Analyzing errors with LLM...")
        try:
            result = self._call_with_retry([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ])
            self.logger.info("Error analysis completed")
            return result
        except Exception as e:
            self.logger.error(f"Failed to analyze error: {e}")
            return f"Error analyzing code: {str(e)}"

    def _clean_output(self, text: str) -> str:
        """Removes markdown code blocks if present."""
        text = text.strip()
        if text.startswith("```python"):
            text = text[9:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()


class CodeRunner:
    """Executes Python code with validation and timeout support."""
    
    def __init__(self, script_path: str = "generated_bot.py"):
        self.script_path = script_path
        self.config = get_config()
        self.logger = get_logger("code_runner")
        self.validator = CodeValidator()

    def validate_code(self, code: str) -> Tuple[bool, List[str]]:
        """Validate code before execution."""
        return self.validator.validate(code)

    def run_code(self, code: str, skip_validation: bool = False) -> Tuple[str, str, bool]:
        """
        Saves the code to a file and runs it.
        Returns (stdout, stderr, success_boolean).
        """
        # Validate unless explicitly skipped
        if not skip_validation:
            is_valid, issues = self.validate_code(code)
            if not is_valid:
                issues_text = "\n".join(f"- {issue}" for issue in issues)
                self.logger.warning(f"Code validation failed: {issues_text}")
                return "", f"Validation failed:\n{issues_text}", False
        
        # Save code
        self.logger.info(f"Saving code to {self.script_path}")
        with open(self.script_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Run code
        self.logger.info(f"Executing code with {self.config.execution_timeout}s timeout")
        try:
            result = subprocess.run(
                ["python", self.script_path],
                capture_output=True,
                text=True,
                timeout=self.config.execution_timeout
            )
            success = result.returncode == 0
            if success:
                self.logger.info("Code execution completed successfully")
            else:
                self.logger.warning(f"Code execution failed with return code {result.returncode}")
            return result.stdout, result.stderr, success
        except subprocess.TimeoutExpired:
            msg = f"Execution timed out after {self.config.execution_timeout} seconds."
            self.logger.error(msg)
            return "", msg, False
        except Exception as e:
            self.logger.error(f"Execution error: {e}")
            return "", str(e), False
