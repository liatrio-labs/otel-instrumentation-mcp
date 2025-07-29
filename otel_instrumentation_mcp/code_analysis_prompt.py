def ask_about_code(code_snippet: str) -> str:
    """Generates a prompt message requesting code analysis and relevant OpenTelemetry documentation.

    Args:
        code_snippet: The code snippet to be analyzed

    Returns:
        A prompt string asking for code analysis and documentation
    """
    prompt = (
        f"Analyze this code snippet:\n\n"
        f"Part 1 - Code Analysis:\n"
        f"1. What does this code do?\n"
        f"Part 2 - Documentation:\n"
        f"1. Check if there is support for this language in OpenTelemetry\n\n"
        f"1. If this language is supported in OpenTelemetry, suggest how to autoinstrument this code\n\n"
        f"2. Always provide URLs to relevant OpenTelemetry documentation for this language\n"
        f"Code snippet:\n{code_snippet}"
    )

    return prompt
