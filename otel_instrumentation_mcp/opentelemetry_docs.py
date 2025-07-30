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

import requests
import re
from markdown import markdown
from bs4 import BeautifulSoup
from opentelemetry.semconv.trace import SpanAttributes

from .telemetry import get_tracer, get_logger, set_span_error, add_span_attributes

tracer = get_tracer()
logger = get_logger()


def get_docs_by_language(language: str):
    with tracer.start_as_current_span("opentelemetry.get_docs_by_language") as span:
        try:
            RAW_BASE_URL = "https://raw.githubusercontent.com/open-telemetry/opentelemetry.io/main/content/en/docs/languages"
            language = language.strip().lower()
            raw_url = f"{RAW_BASE_URL}/{language}/getting-started.md"

            add_span_attributes(
                span,
                **{
                    SpanAttributes.CODE_FUNCTION: "get_docs_by_language",
                    "programming.language": language,
                    SpanAttributes.HTTP_METHOD: "GET",
                    SpanAttributes.HTTP_URL: raw_url,
                },
            )

            logger.info(
                "Fetching OpenTelemetry documentation",
                extra={"language": language, "url": raw_url},
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
                span.add_event("docs_not_found", {"language": language})
                logger.warning(
                    "No documentation found for language", extra={"language": language}
                )
                return {
                    "language": language,
                    "message": f"No docs found for language: {language}",
                }

            response.raise_for_status()

            # Step 1: Convert Markdown to HTML
            with tracer.start_as_current_span("markdown.convert_to_html") as md_span:
                html = markdown(response.text)
                add_span_attributes(
                    md_span, **{"markdown.content_length": len(response.text)}
                )

            # Step 2: Strip HTML tags to get plain text
            with tracer.start_as_current_span("html.extract_text") as html_span:
                soup = BeautifulSoup(html, "html.parser")
                plain_text = soup.get_text()
                add_span_attributes(html_span, **{"html.content_length": len(html)})

            # Step 3: Remove punctuation and normalize whitespace
            with tracer.start_as_current_span("text.clean_and_normalize") as clean_span:
                cleaned_text = re.sub(
                    r"[^\w\s]", "", plain_text
                )  # Remove all punctuation
                cleaned_text = re.sub(
                    r"\s+", " ", cleaned_text
                ).strip()  # Collapse whitespace

                add_span_attributes(
                    clean_span,
                    **{
                        "text.original_length": len(plain_text),
                        "text.cleaned_length": len(cleaned_text),
                    },
                )

            result = {
                "language": language,
                "content": [{"url": raw_url, "cleaned_text": cleaned_text}],
            }

            span.add_event(
                "docs_processed",
                {
                    "language": language,
                    "content_length": len(cleaned_text),
                    "status_code": response.status_code,
                },
            )

            logger.info(
                "Successfully processed OpenTelemetry documentation",
                extra={"language": language, "content_length": len(cleaned_text)},
            )

            return result
        except Exception as e:
            set_span_error(span, e)
            logger.error(
                "Failed to get documentation by language",
                exc_info=True,
                extra={"language": language},
            )
            raise
