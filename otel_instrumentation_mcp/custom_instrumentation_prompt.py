def custom_instrumentation_prompt(code_snippet: str) -> str:
    """Generates a detailed prompt message requesting code analysis and instrumentation
    with OpenTelemetry tracing best practices, suitable for an LLM.

    Args:
        code_snippet: The code snippet to be analyzed

    Returns:
        A detailed prompt string asking for OpenTelemetry instrumentation additions
    """
    prompt = (
        "Review and update the user-provided code snippet by adding appropriate OpenTelemetry tracing using the SDK for the language "
        "Always fetch the OpenTelemetry docs by language first and use them to guide your instrumentation for the language "
        "used in the snippet (e.g., Python, Java, Node.js, Go, etc.).\n\n"
        "Apply the following instrumentation guidelines strictly:\n\n"
        "1. **Custom Span Creation**:\n"
        "   - Create custom spans using the OpenTelemetry API (`start_span`, `with tracer.start_as_current_span`, etc.).\n"
        "   - Add spans inside functions or methods that contain business logic or domain-specific operations.\n"
        "   - Add spans for computation-heavy logic, data processing, or any procedural sequence with meaningful workload.\n"
        "   - Do **not** add spans for trivial operations like variable declarations or simple conditional checks unless they "
        "involve important business decision points.\n\n"
        "2. **Span Enrichment with Log Semantics**:\n"
        "   - Wherever a log message of level INFO or higher (e.g., WARN, ERROR) appears, wrap the corresponding logic in a span.\n"
        "   - If a logger is called (e.g., `logger.info(...)`, `console.log(...)`, etc.), create a span that captures that context.\n"
        "   - Optionally, add logs to the span using the span event/logging API to preserve log message context within the trace.\n\n"
        "3. **Span Attributes**:\n"
        "   - Add span attributes for variables representing user IDs, feature flags, environment flags, tenant IDs, etc.\n"
        "   - Only use attributes that are business-relevant and application-specific.\n"
        "   - Do **NOT** capture or serialize the following types of sensitive information into spans:\n"
        "     - Email addresses\n"
        "     - Credit card numbers or banking data\n"
        "     - Location addresses or physical coordinates\n"
        "     - Any PII unless it is anonymized or explicitly permitted\n\n"
        "4. **Naming and Structure**:\n"
        '   - Name each custom span clearly, using the action being performed (e.g., `"process_order"`, `"fetch_user_data"`).\n'
        "   - Use nested spans if multiple logical steps occur within the same function or if multiple features interact.\n\n"
        "5. **Code Integrity**:\n"
        "   - Do not modify the core logic of the code.\n"
        "   - Ensure the instrumented code compiles/runs correctly.\n"
        "   - Use language-specific OpenTelemetry APIs and idioms.\n\n"
        "Here is the code snippet to analyze and instrument:\n\n"
        "```code\n"
        f"{code_snippet}\n"
        "```"
    )
    return prompt
