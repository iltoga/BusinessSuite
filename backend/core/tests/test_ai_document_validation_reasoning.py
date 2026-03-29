"""Tests for AI document validation reasoning helpers."""

from core.services.ai_document_categorizer import VALIDATION_SCHEMA, format_validation_reasoning
from django.test import SimpleTestCase


class ValidationReasoningFormatTests(SimpleTestCase):
    def test_validation_schema_reasoning_object_branch_disallows_extra_keys(self):
        reasoning_schema = VALIDATION_SCHEMA["properties"]["reasoning"]
        object_branch = next(
            branch
            for branch in reasoning_schema["anyOf"]
            if isinstance(branch, dict) and branch.get("type") == "object"
        )

        self.assertEqual(object_branch["additionalProperties"], False)
        self.assertEqual(
            object_branch["required"],
            ["missing data", "invalid data", "notes", "to do or to ask"],
        )

    def test_formats_descriptive_reasoning_into_missing_data_sections(self):
        output = format_validation_reasoning(
            valid=False,
            reasoning=(
                "While the document contains most required details, "
                "it fails because the passenger name is not visible anywhere."
            ),
            negative_issues=["Passenger name is not visible on the itinerary."],
        )

        self.assertEqual(
            output,
            "missing data: Passenger name is not visible on the itinerary. | "
            "to do or to ask: Request a replacement document that includes the missing data listed above.",
        )
        self.assertNotIn("While the document contains", output)

    def test_formats_invalid_data_sections_when_issue_is_present_but_wrong(self):
        output = format_validation_reasoning(
            valid=False,
            reasoning="",
            negative_issues=["Passport expiration date is expired."],
        )

        self.assertIn("invalid data: Passport expiration date is expired.", output)
        self.assertNotIn("missing data:", output)
        self.assertIn(" | to do or to ask: Correct or replace the invalid data listed above.", output)

    def test_keeps_structured_sections_and_adds_action_when_missing(self):
        output = format_validation_reasoning(
            valid=False,
            reasoning="missing data:\n- Passenger full name",
            negative_issues=[],
        )

        self.assertEqual(
            output,
            "missing data: Passenger full name | "
            "to do or to ask: Request a replacement document that includes the missing data listed above.",
        )

    def test_returns_short_default_for_valid_result_without_reasoning(self):
        output = format_validation_reasoning(valid=True, reasoning="", negative_issues=[])
        self.assertEqual(output, "valid: all required checks passed.")

    def test_formats_structured_object_reasoning(self):
        output = format_validation_reasoning(
            valid=False,
            reasoning={
                "missing data": ["Passenger name is not visible on the document."],
                "notes": ["Travel details are otherwise readable."],
            },
            negative_issues=[],
        )

        self.assertEqual(
            output,
            "missing data: Passenger name is not visible on the document. | "
            "notes: Travel details are otherwise readable. | "
            "to do or to ask: Request a replacement document that includes the missing data listed above.",
        )
