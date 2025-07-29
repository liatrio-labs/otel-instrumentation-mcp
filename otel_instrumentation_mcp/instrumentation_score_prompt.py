def instrumentation_score_analysis_prompt(
    telemetry_data: str = "", service_name: str = "", focus_areas: str = ""
) -> str:
    """Generates a prompt message requesting instrumentation quality analysis using the Instrumentation Score specification.

    Args:
        telemetry_data: Optional telemetry data (traces, metrics, logs) to analyze
        service_name: Optional service name to focus the analysis on
        focus_areas: Optional comma-separated focus areas (e.g., "traces,metrics,resource_attributes")

    Returns:
        A prompt string asking for instrumentation quality analysis based on the Instrumentation Score
    """
    prompt_parts = [
        "Analyze the instrumentation quality using the Instrumentation Score specification:",
        "",
        "Part 1 - Instrumentation Score Assessment:",
        "1. Evaluate the telemetry data against the Instrumentation Score rules",
        "2. Identify which rules are passing and which are failing",
        "3. Calculate an estimated Instrumentation Score (0-100) based on the findings",
        "4. Categorize the score (Excellent: 90-100, Good: 75-89, Needs Improvement: 50-74, Poor: 10-49)",
        "",
        "Part 2 - Detailed Analysis:",
        "1. Break down issues by impact level (Critical, Important, Normal, Low)",
        "2. Identify missing or incorrect resource attributes (service.name, service.version, etc.)",
        "3. Analyze trace quality (span naming, attributes, relationships)",
        "4. Review metric instrumentation patterns",
        "5. Check for high cardinality issues",
        "",
        "Part 3 - Improvement Recommendations:",
        "1. Prioritize fixes based on impact level (Critical first, then Important, etc.)",
        "2. Provide specific, actionable recommendations for each failing rule",
        "3. Suggest OpenTelemetry best practices to improve the score",
        "4. Include relevant semantic convention references",
        "",
        "Part 4 - Implementation Guidance:",
        "1. Provide code examples for fixing the most critical issues",
        "2. Reference relevant OpenTelemetry documentation",
        "3. Suggest monitoring and validation approaches",
    ]

    # Add service-specific context if provided
    if service_name:
        prompt_parts.extend(["", f"Focus on service: {service_name}"])

    # Add focus areas if specified
    if focus_areas:
        focus_list = [area.strip() for area in focus_areas.split(",")]
        prompt_parts.extend(["", f"Pay special attention to: {', '.join(focus_list)}"])

    # Add telemetry data if provided
    if telemetry_data:
        prompt_parts.extend(["", "Telemetry data to analyze:", telemetry_data])
    else:
        prompt_parts.extend(
            [
                "",
                "Note: No specific telemetry data provided. Please provide general guidance on",
                "implementing high-quality OpenTelemetry instrumentation based on the Instrumentation Score rules.",
            ]
        )

    return "\n".join(prompt_parts)


def instrumentation_score_rules_prompt(
    rule_categories: str = "", impact_levels: str = ""
) -> str:
    """Generates a prompt message requesting explanation of Instrumentation Score rules.

    Args:
        rule_categories: Optional comma-separated rule categories (e.g., "RES,SPA,MET")
        impact_levels: Optional comma-separated impact levels (e.g., "Critical,Important")

    Returns:
        A prompt string asking for explanation of Instrumentation Score rules
    """
    prompt_parts = [
        "Explain the Instrumentation Score rules and their importance:",
        "",
        "Part 1 - Rule Overview:",
        "1. Provide a summary of the Instrumentation Score rule system",
        "2. Explain the impact levels (Critical, Important, Normal, Low) and their weights",
        "3. Describe how the scoring calculation works",
        "",
        "Part 2 - Rule Categories:",
        "1. Break down rules by category (Resource, Span, Metric, Log, SDK)",
        "2. Explain the purpose and rationale for each category",
        "3. Provide examples of common violations and their impact",
        "",
        "Part 3 - Implementation Guidance:",
        "1. Suggest how to implement monitoring for these rules",
        "2. Provide best practices for maintaining high scores",
        "3. Recommend tools and approaches for continuous assessment",
    ]

    # Add category filter if specified
    if rule_categories:
        categories = [cat.strip() for cat in rule_categories.split(",")]
        prompt_parts.extend(["", f"Focus on rule categories: {', '.join(categories)}"])

    # Add impact level filter if specified
    if impact_levels:
        levels = [level.strip() for level in impact_levels.split(",")]
        prompt_parts.extend(["", f"Focus on impact levels: {', '.join(levels)}"])

    return "\n".join(prompt_parts)
