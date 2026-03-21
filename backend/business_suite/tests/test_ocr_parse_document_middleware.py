from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from business_suite.middlewares.ocr_parse_document import OcrParseDocumentMiddleware


class OcrParseDocumentMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("business_suite.middlewares.ocr_parse_document.extract_mrz_data", return_value="parsed-mrz-data")
    def test_injects_extracted_data_into_post_and_calls_next_handler(self, extract_mrz_data_mock):
        uploaded_file = SimpleUploadedFile("passport.jpg", b"passport-bytes", content_type="image/jpeg")
        request = self.factory.post("/api/ocr/", {"file": uploaded_file})
        get_response = Mock(side_effect=lambda req: HttpResponse(req.POST["data"]))

        middleware = OcrParseDocumentMiddleware(get_response)
        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "parsed-mrz-data")
        self.assertEqual(request.POST["data"], "parsed-mrz-data")
        extract_mrz_data_mock.assert_called_once()
        extracted_file = extract_mrz_data_mock.call_args.args[0]
        self.assertEqual(extracted_file.name, uploaded_file.name)
        self.assertEqual(extracted_file.content_type, uploaded_file.content_type)
        get_response.assert_called_once()

    @patch("business_suite.middlewares.ocr_parse_document.extract_mrz_data", side_effect=FileNotFoundError)
    def test_returns_json_error_when_file_is_missing(self, extract_mrz_data_mock):
        uploaded_file = SimpleUploadedFile("passport.jpg", b"passport-bytes", content_type="image/jpeg")
        request = self.factory.post("/api/ocr/", {"file": uploaded_file})
        get_response = Mock(return_value=HttpResponse("ok"))

        middleware = OcrParseDocumentMiddleware(get_response)
        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), {"error": "The specified file could not be found"})
        extract_mrz_data_mock.assert_called_once()
        get_response.assert_not_called()

    @patch("business_suite.middlewares.ocr_parse_document.extract_mrz_data", side_effect=RuntimeError("boom"))
    def test_returns_json_error_when_extraction_fails(self, extract_mrz_data_mock):
        uploaded_file = SimpleUploadedFile("passport.jpg", b"passport-bytes", content_type="image/jpeg")
        request = self.factory.post("/api/ocr/", {"file": uploaded_file})
        get_response = Mock(return_value=HttpResponse("ok"))

        middleware = OcrParseDocumentMiddleware(get_response)
        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content.decode(),
            {"error": "An unexpected error occurred: boom"},
        )
        extract_mrz_data_mock.assert_called_once()
        get_response.assert_not_called()
