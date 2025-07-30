# Copyright 2025 Liatrio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


def autoinstrumentation_prompt(code_snippet: str) -> str:
    """Generates a prompt message requesting code analysis and relevant OpenTelemetry documentation.

    Args:
        code_snippet: The code snippet to be analyzed

    Returns:
        A prompt string asking for code analysis and documentation
    """
    prompt = (
        f"Review the user-provided code snippet and check if there is support for this language in OpenTelemetry:\n\n"
        f"1. If this language is supported in OpenTelemetry, suggest how to autoinstrument this code\n\n"
        f"2. Add tracing, logging, and metrics to the code using OpenTelemetry autoinstrumentation\n"
        f"3. Always provide URLs to relevant OpenTelemetry documentation for this language\n"
        f"Code snippet:\n{code_snippet}"
    )

    return prompt
