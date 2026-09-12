"""Tests for ContentRatingConfig — the jurisdiction preference bucket (ADR-035)."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.settings.domain.value_objects import ContentRatingConfig
from src.shared_kernel.content_policy import ContentRatingFallback


@pytest.mark.unit
class TestDefaults:
    """The factory default has to reproduce today's behaviour."""

    def test_should_default_to_brazil_then_united_states(self):
        assert ContentRatingConfig().jurisdictions == ["BR", "US"]

    def test_should_default_to_strictest_available(self):
        assert ContentRatingConfig().fallback is ContentRatingFallback.STRICTEST_AVAILABLE


@pytest.mark.unit
class TestNormalization:
    """Operators type country codes by hand, in the admin form."""

    def test_should_upper_case_and_trim(self):
        assert ContentRatingConfig(jurisdictions=[" br ", "us"]).jurisdictions == ["BR", "US"]

    def test_should_drop_duplicates_keeping_the_first(self):
        """Order is the whole meaning of the field, so de-dup must not sort."""
        config = ContentRatingConfig(jurisdictions=["US", "BR", "us"])

        assert config.jurisdictions == ["US", "BR"]

    def test_should_drop_blank_entries(self):
        assert ContentRatingConfig(jurisdictions=["BR", "", "  "]).jurisdictions == ["BR"]

    def test_should_accept_an_empty_preference(self):
        """No preference is legal — every title then takes the fallback path."""
        assert ContentRatingConfig(jurisdictions=[]).jurisdictions == []

    def test_should_treat_none_as_empty(self):
        assert ContentRatingConfig(jurisdictions=None).jurisdictions == []


@pytest.mark.unit
class TestValidation:
    """A bad code must fail at write time, not when a title is enriched."""

    @pytest.mark.parametrize("bad", ["BRA", "B", "B1", "12", "BR-SP"])
    def test_should_reject_anything_that_is_not_a_country_code(self, bad):
        with pytest.raises(DomainValidationException):
            ContentRatingConfig(jurisdictions=[bad])

    def test_should_reject_an_unknown_fallback(self):
        with pytest.raises(DomainValidationException):
            ContentRatingConfig(fallback="whatever")

    def test_should_be_immutable(self):
        config = ContentRatingConfig()

        with pytest.raises(DomainValidationException):
            config.jurisdictions = ["US"]


@pytest.mark.unit
class TestPersistenceRoundTrip:
    """The bucket is stored as JSON in ``app_settings``.

    A row that fails to revalidate takes down the whole RuntimeSettings
    refresh, so the round-trip is load-bearing.
    """

    def test_should_survive_dump_and_revalidate(self):
        config = ContentRatingConfig(
            jurisdictions=["ES", "FR"],
            fallback=ContentRatingFallback.NONE,
        )

        assert ContentRatingConfig(**config.model_dump(mode="json")) == config

    def test_should_dump_the_fallback_as_a_plain_string(self):
        dumped = ContentRatingConfig().model_dump(mode="json")

        assert dumped["fallback"] == "strictest_available"

    def test_with_updates_should_produce_a_new_valid_config(self):
        config = ContentRatingConfig().with_updates(jurisdictions=["pt"])

        assert config.jurisdictions == ["PT"]
        assert config.fallback is ContentRatingFallback.STRICTEST_AVAILABLE
