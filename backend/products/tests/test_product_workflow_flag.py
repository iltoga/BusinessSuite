from django.test import TestCase

from products.models import Product, Task


class ProductWorkflowFlagTests(TestCase):
    def test_flag_is_false_for_products_without_docs_and_tasks(self):
        product = Product.objects.create(name="No Workflow", code="NO-WF-1", product_type="other")
        self.assertFalse(product.uses_customer_app_workflow)

    def test_flag_is_true_when_documents_are_configured(self):
        product = Product.objects.create(
            name="Docs Workflow",
            code="DOC-WF-1",
            product_type="visa",
            required_documents="Passport",
        )
        self.assertTrue(product.uses_customer_app_workflow)

    def test_flag_is_true_when_tasks_are_configured(self):
        product = Product.objects.create(name="Task Workflow", code="TASK-WF-1", product_type="visa")
        Task.objects.create(
            product=product,
            step=1,
            name="Collect",
            duration=1,
            duration_is_business_days=False,
        )
        product.refresh_from_db()
        self.assertTrue(product.uses_customer_app_workflow)

    def test_flag_recomputes_to_false_after_last_task_removed(self):
        product = Product.objects.create(name="Task Workflow 2", code="TASK-WF-2", product_type="visa")
        task = Task.objects.create(
            product=product,
            step=1,
            name="Collect",
            duration=1,
            duration_is_business_days=False,
        )
        task.delete()
        product.refresh_from_db()
        self.assertFalse(product.uses_customer_app_workflow)
