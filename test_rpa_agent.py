import unittest
from unittest.mock import MagicMock, patch
import os
from rpa_agent import Recorder, LLMClient, CodeRunner

class TestRPAAgent(unittest.TestCase):

    def test_recorder_file_handling(self):
        recorder = Recorder()
        # Verify path is set (file might not exist yet if not recorded)
        self.assertTrue(recorder.output_path.endswith("playwright_recording_temp.py"))
        
        # Write some dummy data to simulate recording
        with open(recorder.output_path, "w") as f:
            f.write("print('Recorded')")
        
        # Now verify file exists
        self.assertTrue(os.path.exists(recorder.output_path))
            
        code = recorder.get_recorded_code()
        self.assertEqual(code, "print('Recorded')")

    @patch('rpa_agent.OpenAI')
    def test_llm_client_refine(self, mock_openai):
        # Mock the API response
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "```python\nprint('Refined')\n```"
        mock_openai.return_value.chat.completions.create.return_value = mock_response

        client = LLMClient("key", "url", "model")
        result = client.refine_code("intent", "raw_code")
        
        self.assertEqual(result, "print('Refined')")

    def test_code_runner_success(self):
        runner = CodeRunner("test_script.py")
        stdout, stderr, success = runner.run_code("print('Hello World')")
        self.assertTrue(success)
        self.assertIn("Hello World", stdout)
        if os.path.exists("test_script.py"):
            os.remove("test_script.py")

    def test_code_runner_failure(self):
        runner = CodeRunner("test_fail.py")
        stdout, stderr, success = runner.run_code("raise Exception('Boom')")
        self.assertFalse(success)
        self.assertIn("Boom", stderr)
        if os.path.exists("test_fail.py"):
            os.remove("test_fail.py")

if __name__ == '__main__':
    unittest.main()
