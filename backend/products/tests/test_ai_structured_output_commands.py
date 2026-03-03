import io
import json

from django.core.management import call_command
from django.test import TestCase
from products.models.document_type import DocumentType


class AIStructuredOutputCommandsTests(TestCase):
    def setUp(self):
        # create a few document types with known rules
        DocumentType.objects.bulk_create(
            [
                DocumentType(
                    name="Test Doc 1",
                    description="A test document",
                    validation_rule_ai_positive="Look for: field one, field two and field three.",
                    ai_structured_output="",
                ),
                DocumentType(
                    name="NoRule",
                    description="Has no rule text",
                    validation_rule_ai_positive="",
                ),
                DocumentType(
                    name="BulletDoc",
                    description="Has bullets",
                    validation_rule_ai_positive="""
                    Validate this as something. Look for:
                    - first item
                    - second item and additional detail
                    - third
                """,
                ),
            ]
        )

    def test_extract_command_outputs_expected_structure(self):
        out = io.StringIO()
        call_command("extract_ai_structured_output", stdout=out)
        output = out.getvalue()
        # each document name should appear
        self.assertIn("Test Doc 1", output)
        self.assertIn("NoRule", output)
        self.assertIn("BulletDoc", output)
        # the generated json for Test Doc 1 should include our fields
        self.assertIn("field_one", output)
        self.assertIn("field_two", output)
        self.assertIn("field_three", output)

    def test_update_command_persists_json(self):
        # run update once
        out = io.StringIO()
        call_command("update_ai_structured_output", stdout=out)
        # reload objects
        dt1 = DocumentType.objects.get(name="Test Doc 1")
        self.assertTrue(dt1.ai_structured_output)
        data = json.loads(dt1.ai_structured_output)
        # expecting three entries
        field_names = {f["field_name"] for f in data}
        self.assertSetEqual(field_names, {"field_one", "field_two", "field_three"})
        # subsequent run shouldn't change the field again
        prev = dt1.ai_structured_output
        out2 = io.StringIO()
        call_command("update_ai_structured_output", stdout=out2)
        dt1.refresh_from_db()
        self.assertEqual(prev, dt1.ai_structured_output)
        self.assertIn("No change for Test Doc 1", out2.getvalue())
