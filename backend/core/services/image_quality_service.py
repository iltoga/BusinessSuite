from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Optional

import numpy as np
from core.services.logger_service import Logger

logger = Logger.get_logger(__name__)


@dataclass
class ImageQualityResult:
    is_good_quality: bool
    analyzer_available: bool
    rejection_code: Optional[str] = None
    rejection_reason: Optional[str] = None
    width: int = 0
    height: int = 0
    laplacian_variance: float = 0.0
    mean_gradient_magnitude: float = 0.0
    edge_density: float = 0.0
    brightness_mean: float = 0.0
    contrast_std: float = 0.0
    dynamic_range_p95_p5: float = 0.0
    clipped_dark_ratio: float = 0.0
    clipped_bright_ratio: float = 0.0
    mrz_roi_laplacian_variance: float = 0.0
    bottom_edge_dark_ratio: float = 0.0
    bottom_edge_edge_density: float = 0.0
    mrz_cutoff_suspected: bool = False
    quality_score: float = 0.0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_good_quality": self.is_good_quality,
            "analyzer_available": self.analyzer_available,
            "rejection_code": self.rejection_code,
            "rejection_reason": self.rejection_reason,
            "width": self.width,
            "height": self.height,
            "laplacian_variance": self.laplacian_variance,
            "mean_gradient_magnitude": self.mean_gradient_magnitude,
            "edge_density": self.edge_density,
            "brightness_mean": self.brightness_mean,
            "contrast_std": self.contrast_std,
            "dynamic_range_p95_p5": self.dynamic_range_p95_p5,
            "clipped_dark_ratio": self.clipped_dark_ratio,
            "clipped_bright_ratio": self.clipped_bright_ratio,
            "mrz_roi_laplacian_variance": self.mrz_roi_laplacian_variance,
            "bottom_edge_dark_ratio": self.bottom_edge_dark_ratio,
            "bottom_edge_edge_density": self.bottom_edge_edge_density,
            "mrz_cutoff_suspected": self.mrz_cutoff_suspected,
            "quality_score": self.quality_score,
            "notes": self.notes,
        }


class ImageQualityService:
    """
    OpenCV-based quality analyzer for document photos.

    Main blur detector: variance of Laplacian (per PyImageSearch + referenced papers)
    with additional quality heuristics to catch low-light, overexposure, and low-detail scans.
    """

    def __init__(
        self,
        min_laplacian_variance: float = 160.0,
        hard_blur_laplacian_threshold: float = 45.0,
        min_mrz_roi_laplacian_variance: float = 70.0,
        bottom_edge_strip_ratio: float = 0.01,
        max_bottom_edge_dark_ratio: float = 0.15,
        max_bottom_edge_edge_density: float = 0.14,
        min_mean_gradient_magnitude: float = 12.0,
        min_edge_density: float = 0.008,
        min_contrast_std: float = 18.0,
        min_dynamic_range_p95_p5: float = 45.0,
        min_short_side_px: int = 700,
        brightness_min: float = 55.0,
        brightness_max: float = 215.0,
        max_clipped_dark_ratio: float = 0.30,
        max_clipped_bright_ratio: float = 0.30,
    ):
        self.min_laplacian_variance = min_laplacian_variance
        self.hard_blur_laplacian_threshold = hard_blur_laplacian_threshold
        self.min_mrz_roi_laplacian_variance = min_mrz_roi_laplacian_variance
        self.bottom_edge_strip_ratio = bottom_edge_strip_ratio
        self.max_bottom_edge_dark_ratio = max_bottom_edge_dark_ratio
        self.max_bottom_edge_edge_density = max_bottom_edge_edge_density
        self.min_mean_gradient_magnitude = min_mean_gradient_magnitude
        self.min_edge_density = min_edge_density
        self.min_contrast_std = min_contrast_std
        self.min_dynamic_range_p95_p5 = min_dynamic_range_p95_p5
        self.min_short_side_px = min_short_side_px
        self.brightness_min = brightness_min
        self.brightness_max = brightness_max
        self.max_clipped_dark_ratio = max_clipped_dark_ratio
        self.max_clipped_bright_ratio = max_clipped_bright_ratio

    def evaluate(self, file_content: bytes) -> ImageQualityResult:
        cv2 = self._load_cv2()
        if cv2 is None:
            return ImageQualityResult(
                is_good_quality=True,
                analyzer_available=False,
                rejection_code=None,
                rejection_reason=None,
                notes=["OpenCV not installed; skipped deterministic quality checks."],
            )

        image = self._decode_image(cv2, file_content)
        if image is None:
            return ImageQualityResult(
                is_good_quality=False,
                analyzer_available=True,
                rejection_code="invalid_image",
                rejection_reason="Unable to decode image bytes. Please upload a valid image file.",
                notes=["cv2.imdecode returned None"],
            )

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape[:2]

        laplacian_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        # Passport MRZ zone is typically in the lower area; ensure this region is sharp enough.
        mrz_top = int(height * 0.72)
        mrz_roi = gray[mrz_top:height, :]
        mrz_roi_laplacian_variance = (
            float(cv2.Laplacian(mrz_roi, cv2.CV_64F).var()) if mrz_roi.size else laplacian_variance
        )

        sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = cv2.magnitude(sobel_x, sobel_y)
        mean_gradient_magnitude = float(np.mean(grad_mag))

        edges = cv2.Canny(gray, 80, 160)
        edge_density = float(np.count_nonzero(edges)) / float(edges.size)

        # Cropped-MRZ heuristic: if the last MRZ line is cut, bottom-most rows contain dense
        # dark/edge content touching the frame border.
        bottom_h = max(4, int(height * self.bottom_edge_strip_ratio))
        bottom_strip = gray[height - bottom_h : height, :]
        bottom_edges = cv2.Canny(bottom_strip, 80, 160)
        bottom_edge_dark_ratio = float(np.mean(bottom_strip < 150)) if bottom_strip.size else 0.0
        bottom_edge_edge_density = float(np.mean(bottom_edges > 0)) if bottom_edges.size else 0.0
        mrz_cutoff_suspected = (
            bottom_edge_dark_ratio > self.max_bottom_edge_dark_ratio
            and bottom_edge_edge_density > self.max_bottom_edge_edge_density
        )

        mean_arr, std_arr = cv2.meanStdDev(gray)
        brightness_mean = float(mean_arr[0][0])
        contrast_std = float(std_arr[0][0])

        p5, p95 = np.percentile(gray, [5, 95])
        dynamic_range_p95_p5 = float(p95 - p5)

        clipped_dark_ratio = float(np.mean(gray <= 10))
        clipped_bright_ratio = float(np.mean(gray >= 245))

        reasons: list[str] = []
        rejection_code: Optional[str] = None

        if min(width, height) < self.min_short_side_px:
            rejection_code = "image_low_resolution"
            reasons.append(
                f"Image resolution is too low ({width}x{height}). Minimum short side is {self.min_short_side_px}px."
            )

        if mrz_cutoff_suspected:
            rejection_code = "mrz_cropped"
            reasons.append(
                "The bottom MRZ line appears cut/cropped at the image edge. Please upload the full passport page with both full MRZ lines visible."
            )

        if brightness_mean < self.brightness_min:
            rejection_code = rejection_code or "image_too_dark"
            reasons.append("Image is too dark. Increase light and avoid underexposure.")
        elif brightness_mean > self.brightness_max:
            rejection_code = rejection_code or "image_too_bright"
            reasons.append("Image is too bright. Avoid glare/overexposure and reduce direct reflections.")

        if clipped_dark_ratio > self.max_clipped_dark_ratio:
            rejection_code = rejection_code or "image_shadow_clipping"
            reasons.append("Large dark clipped area detected (heavy shadows/underexposure).")

        if clipped_bright_ratio > self.max_clipped_bright_ratio:
            rejection_code = rejection_code or "image_glare"
            reasons.append("Large bright clipped area detected (glare or overexposure).")

        if contrast_std < self.min_contrast_std:
            rejection_code = rejection_code or "image_low_contrast"
            reasons.append("Image contrast is too low. Increase lighting and avoid flat shadows.")

        if contrast_std < self.min_contrast_std and dynamic_range_p95_p5 < self.min_dynamic_range_p95_p5:
            rejection_code = rejection_code or "image_low_dynamic_range"
            reasons.append("Image dynamic range is too narrow. Highlights/shadows are not well separated.")

        blur_flags = [
            laplacian_variance < self.min_laplacian_variance,
            mrz_roi_laplacian_variance < self.min_mrz_roi_laplacian_variance,
            mean_gradient_magnitude < self.min_mean_gradient_magnitude,
            edge_density < self.min_edge_density,
        ]

        # Hard blur guard: extremely low Laplacian variance is a strong blur signal.
        if laplacian_variance < self.hard_blur_laplacian_threshold:
            rejection_code = rejection_code or "image_blurry"
            reasons.append(
                "Image is too blurry for reliable OCR (very low sharpness). Please upload a sharper passport image."
            )
        elif sum(1 for flag in blur_flags if flag) >= 2:
            rejection_code = rejection_code or "image_blurry"
            reasons.append("Image appears blurry (insufficient sharp edges/focus). Please upload a sharper image.")

        # Lightweight quality score in [0,1] for diagnostics.
        score_terms = [
            min(laplacian_variance / max(self.min_laplacian_variance, 1e-6), 1.0),
            min(mean_gradient_magnitude / max(self.min_mean_gradient_magnitude, 1e-6), 1.0),
            min(edge_density / max(self.min_edge_density, 1e-6), 1.0),
            min(contrast_std / max(self.min_contrast_std, 1e-6), 1.0),
            min(dynamic_range_p95_p5 / max(self.min_dynamic_range_p95_p5, 1e-6), 1.0),
            1.0 if self.brightness_min <= brightness_mean <= self.brightness_max else 0.6,
            max(0.0, 1.0 - clipped_dark_ratio / max(self.max_clipped_dark_ratio, 1e-6)),
            max(0.0, 1.0 - clipped_bright_ratio / max(self.max_clipped_bright_ratio, 1e-6)),
        ]
        quality_score = float(np.clip(np.mean(score_terms), 0.0, 1.0))

        return ImageQualityResult(
            is_good_quality=not reasons,
            analyzer_available=True,
            rejection_code=rejection_code,
            rejection_reason=" ".join(reasons) if reasons else None,
            width=width,
            height=height,
            laplacian_variance=laplacian_variance,
            mean_gradient_magnitude=mean_gradient_magnitude,
            edge_density=edge_density,
            brightness_mean=brightness_mean,
            contrast_std=contrast_std,
            dynamic_range_p95_p5=dynamic_range_p95_p5,
            clipped_dark_ratio=clipped_dark_ratio,
            clipped_bright_ratio=clipped_bright_ratio,
            mrz_roi_laplacian_variance=mrz_roi_laplacian_variance,
            bottom_edge_dark_ratio=bottom_edge_dark_ratio,
            bottom_edge_edge_density=bottom_edge_edge_density,
            mrz_cutoff_suspected=mrz_cutoff_suspected,
            quality_score=quality_score,
            notes=reasons,
        )

    @staticmethod
    def _load_cv2():
        try:
            return import_module("cv2")
        except Exception as exc:
            logger.warning("OpenCV unavailable for image quality analysis: %s", exc)
            return None

    @staticmethod
    def _decode_image(cv2: Any, file_content: bytes):
        np_buffer = np.frombuffer(file_content, dtype=np.uint8)
        if np_buffer.size == 0:
            return None
        return cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
