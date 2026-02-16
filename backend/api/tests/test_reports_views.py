from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.reports_views import CustomerLifetimeValueApiView


class CustomerLifetimeValueApiViewTests(TestCase):
    def test_customer_ltv_api_omits_non_serializable_customer_objects(self):
        request = APIRequestFactory().get("/api/reports/customer-ltv/")
        user = get_user_model().objects.create_user(username="reporter", password="secret")
        force_authenticate(request, user=user)

        context = {
            "top_customers": [],
            "all_customers": [
                {
                    "customer": SimpleNamespace(id=42),
                    "customer_name": "Acme Ltd",
                    "customer_id": 42,
                    "total_revenue": 1234.56,
                }
            ],
            "total_customers": 1,
            "total_revenue": 1234.56,
            "total_revenue_formatted": "$1,234.56",
            "avg_customer_value": 1234.56,
            "avg_customer_value_formatted": "$1,234.56",
            "high_value_count": 1,
            "medium_value_count": 0,
            "low_value_count": 0,
        }

        with patch.object(CustomerLifetimeValueApiView, "build_context", return_value=context):
            response = CustomerLifetimeValueApiView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        response.render()

        payload = response.data
        self.assertNotIn("all_customers", payload)
        self.assertEqual(
            payload["top_customers"],
            [
                {
                    "customer_name": "Acme Ltd",
                    "customer_id": 42,
                    "total_revenue": 1234.56,
                }
            ],
        )
