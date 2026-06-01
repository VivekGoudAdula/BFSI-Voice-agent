"""Tests for multilingual detection and switching."""

import pytest

from app.services.language_detection_service import LanguageDetectionService

SUPPORTED = ["en", "hi", "te", "ta", "kn", "mr", "bn"]


@pytest.fixture
def detection() -> LanguageDetectionService:
    return LanguageDetectionService()


def test_switch_request_hindi(detection: LanguageDetectionService) -> None:
    assert detection.detect_switch_request("Can you speak Hindi?", SUPPORTED) == "hi"


def test_switch_request_telugu(detection: LanguageDetectionService) -> None:
    assert (
        detection.detect_switch_request("తెలుగులో మాట్లాడండి", SUPPORTED) == "te"
    )


def test_switch_request_english(detection: LanguageDetectionService) -> None:
    assert detection.detect_switch_request("I prefer English.", SUPPORTED) == "en"


def test_switch_request_hindi_phrase(detection: LanguageDetectionService) -> None:
    assert detection.detect_switch_request("Hindi mein baat karo.", SUPPORTED) == "hi"


def test_detect_hindi_script(detection: LanguageDetectionService) -> None:
    result = detection.detect_language(
        "मेरा EMI कब due है?",
        supported=SUPPORTED,
        previous_language="en",
    )
    assert result.language == "hi"
    assert result.confidence > 0.5


def test_detect_telugu_script(detection: LanguageDetectionService) -> None:
    result = detection.detect_language(
        "నా EMI ఎప్పుడు చెల్లించాలి?",
        supported=SUPPORTED,
        previous_language="en",
    )
    assert result.language == "te"
