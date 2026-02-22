import importlib.util

import numpy as np
from core.services.image_quality_service import ImageQualityService
from django.test import SimpleTestCase

CV2_AVAILABLE = importlib.util.find_spec("cv2") is not None


class ImageQualityServiceTestCase(SimpleTestCase):
    @staticmethod
    def _encode_png(image: np.ndarray) -> bytes:
        cv2 = __import__("cv2")
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise RuntimeError("Failed to encode PNG for test")
        return encoded.tobytes()

    def setUp(self):
        if not CV2_AVAILABLE:
            self.skipTest("OpenCV (cv2) is not installed in this environment")
        self.service = ImageQualityService()

    def test_sharp_document_like_image_is_good_quality(self):
        cv2 = __import__("cv2")
        # Build a synthetic "document-like" image: neutral paper background + crisp text/lines.
        image = np.full((1400, 1000, 3), 180, dtype=np.uint8)
        cv2.rectangle(image, (80, 80), (920, 1320), (40, 40, 40), 4)
        cv2.line(image, (120, 280), (880, 280), (20, 20, 20), 3)
        cv2.line(image, (120, 360), (880, 360), (20, 20, 20), 3)
        cv2.putText(image, "PASSPORT", (130, 230), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (10, 10, 10), 4)
        cv2.putText(image, "SURNAME: ROSSI", (130, 470), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (10, 10, 10), 3)
        cv2.putText(image, "NAME: MARIO", (130, 560), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (10, 10, 10), 3)
        cv2.putText(
            image, "P<ITAROSSI<<MARIO<<<<<<<<<<<<<<<<<<<<", (130, 1180), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (5, 5, 5), 2
        )
        cv2.putText(
            image, "YA1234567ITA850315M300109<<<<<<<<<<<<", (130, 1240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (5, 5, 5), 2
        )
        file_bytes = self._encode_png(image)

        result = self.service.evaluate(file_bytes)

        self.assertTrue(result.analyzer_available)
        self.assertTrue(result.is_good_quality)
        self.assertGreater(result.laplacian_variance, 160.0)

    def test_strongly_blurred_image_is_rejected(self):
        cv2 = __import__("cv2")
        tile = np.array([[0, 255], [255, 0]], dtype=np.uint8)
        gray = np.tile(tile, (600, 900))
        blurred = cv2.GaussianBlur(gray, (31, 31), 0)
        image = np.stack([blurred, blurred, blurred], axis=-1)
        file_bytes = self._encode_png(image)

        result = self.service.evaluate(file_bytes)

        self.assertTrue(result.analyzer_available)
        self.assertFalse(result.is_good_quality)
        self.assertTrue(
            any(token in (result.rejection_reason or "") for token in ["blurry", "contrast", "dynamic range", "sharp"])
        )

    def test_overexposed_image_is_rejected(self):
        gray = np.full((1200, 900), 250, dtype=np.uint8)
        image = np.stack([gray, gray, gray], axis=-1)
        file_bytes = self._encode_png(image)

        result = self.service.evaluate(file_bytes)

        self.assertTrue(result.analyzer_available)
        self.assertFalse(result.is_good_quality)
        self.assertTrue(
            any(
                token in (result.rejection_reason or "")
                for token in ["too bright", "glare", "overexposure", "contrast"]
            )
        )

    def test_bottom_edge_mrz_cut_is_rejected(self):
        cv2 = __import__("cv2")
        image = np.full((1200, 900, 3), 230, dtype=np.uint8)
        # Simulate MRZ text touching the bottom edge (cropped last line effect)
        cv2.putText(
            image,
            "P<ITAROSSI<<MARIO<<<<<<<<<<<<<<<<<<<<",
            (60, 1188),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (15, 15, 15),
            2,
        )
        cv2.putText(
            image,
            "YA1234567ITA850315M300109<<<<<<<<<<<<",
            (30, 1199),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (15, 15, 15),
            2,
        )

        file_bytes = self._encode_png(image)
        result = self.service.evaluate(file_bytes)

        self.assertFalse(result.is_good_quality)
        self.assertTrue(result.mrz_cutoff_suspected)
        self.assertEqual(result.rejection_code, "mrz_cropped")
