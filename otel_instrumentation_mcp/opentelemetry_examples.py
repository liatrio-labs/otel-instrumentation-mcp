import os
import requests
from opentelemetry.semconv.trace import SpanAttributes

from .telemetry import get_tracer, get_logger, set_span_error, add_span_attributes

GITHUB_API_URL = os.getenv("GITHUB_REST_URL", "https://api.github.com")
OPENTELEMETRY_DOCS_REPO = os.getenv(
    "OPENTELEMETRY_DOCS_REPO", "open-telemetry/opentelemetry.io"
)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

tracer = get_tracer()
logger = get_logger()


def get_demo_services_doc():
    with tracer.start_as_current_span("github.get_demo_services_doc") as span:
        try:
            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "get_demo_services_doc",
                    "github.repository": OPENTELEMETRY_DOCS_REPO,
                    "github.file.path": "content/en/docs/demo/services/_index.md",
                },
            )

            # Use public GitHub raw URL instead of API to avoid auth requirement
            path = "content/en/docs/demo/services/_index.md"
            raw_url = f"https://raw.githubusercontent.com/{OPENTELEMETRY_DOCS_REPO}/main/{path}"

            # Add HTTP semantic conventions for the raw content request
            add_span_attributes(
                span,
                **{
                    SpanAttributes.HTTP_METHOD: "GET",
                    SpanAttributes.HTTP_URL: raw_url,
                },
            )

            logger.info(
                "Fetching demo services documentation from raw GitHub",
                extra={
                    "repository": OPENTELEMETRY_DOCS_REPO,
                    "path": path,
                    "url": raw_url,
                },
            )

            response = requests.get(raw_url)

            add_span_attributes(
                span,
                **{
                    SpanAttributes.HTTP_STATUS_CODE: response.status_code,
                    SpanAttributes.HTTP_RESPONSE_CONTENT_LENGTH: len(response.content),
                },
            )

            if response.status_code == 404:
                span.add_event("file_not_found", {"path": path})
                logger.warning("Demo services file not found", extra={"path": path})
                return {"error": f"Could not find file at path: {path}"}

            response.raise_for_status()
            content = response.text

            span.add_event(
                "demo_services_doc_fetched",
                {
                    "content_length": len(content),
                    "file_url": f"https://github.com/{OPENTELEMETRY_DOCS_REPO}/blob/main/{path}",
                },
            )

            logger.info(
                "Successfully fetched demo services documentation",
                extra={"content_length": len(content)},
            )

            return {
                "url": f"https://github.com/{OPENTELEMETRY_DOCS_REPO}/blob/main/{path}",
                "content": content,
            }
        except Exception as e:
            set_span_error(span, e)
            logger.error("Failed to fetch demo services documentation", exc_info=True)
            raise


def get_demo_services_by_language(language: str):
    with tracer.start_as_current_span(
        "opentelemetry.get_demo_services_by_language"
    ) as span:
        try:
            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "get_demo_services_by_language",
                    "programming.language": language,
                },
            )

            services_by_language = {
                ".NET": ["accounting", "cart"],
                "Java": ["ad"],
                "Go": ["checkout", "product-catalog"],
                "C++": ["currency"],
                "Ruby": ["email"],
                "Kotlin": ["fraud-detection"],
                "TypeScript": ["frontend", "react-native-app"],
                "Python/Locust": ["load-generator"],
                "JavaScript": ["payment"],
                "Python": ["recommendation"],
                "PHP": ["quote"],
                "Rust": ["shipping"],
            }
            BASE_URL = (
                "https://github.com/open-telemetry/opentelemetry-demo/tree/main/src"
            )
            language = language.strip().lower()

            logger.info(
                "Looking up demo services by language", extra={"language": language}
            )

            matched = [
                (lang, services)
                for lang, services in services_by_language.items()
                if lang.lower() == language
            ]

            if not matched:
                span.add_event("language_not_found", {"language": language})
                logger.warning(
                    "No services found for language", extra={"language": language}
                )
                return {
                    "language": language,
                    "services": [],
                    "message": f"No services found for language: {language}",
                }

            lang, services = matched[0]

            add_span_attributes(
                span,
                **{
                    "services.count": len(services),
                    "language.matched": lang,
                },
            )

            result = {
                "language": lang,
                "services": [
                    {"name": service, "url": f"{BASE_URL}/{service}"}
                    for service in services
                ],
            }

            span.add_event(
                "services_found", {"language": lang, "services_count": len(services)}
            )

            logger.info(
                "Successfully found demo services by language",
                extra={"language": lang, "services_count": len(services)},
            )

            return result
        except Exception as e:
            set_span_error(span, e)
            logger.error(
                "Failed to get demo services by language",
                exc_info=True,
                extra={"language": language},
            )
            raise
