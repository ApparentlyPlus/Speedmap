"""Reading Vodafone's service qualification."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from probe.adapter import Target
from probe.vodafone import Vodafone, cabinet, mbps, offers, read

DSLAM = {
    "category": "DSLAM",
    "resourceCharacteristic": [
        {"name": "name", "value": "447 - ΑΘΗΝΑΣ"},
        {"name": "kvid", "value": "0174"},
    ],
}

# Shaped as their endpoint answers: a category per technology, speeds as strings, and
# fixed wireless qualified with no service attached to it at all.
ANSWER: dict[str, Any] = {
    "serviceQualificationItem": [
        {"category": {"name": "FWA"}, "service": {"supportingResource": [DSLAM]}},
        {
            "category": {"name": "ADSL"},
            "service": {
                "supportingResource": [DSLAM],
                "supportingService": [{
                    "name": "ADSL",
                    "serviceCharacteristic": [
                        {"name": "maxPromisedSpeedDownload", "value": "15.22"},
                        {"name": "averagePromisedSpeedDownload", "value": "11.24"},
                        {"name": "averagePromisedSpeedUpload", "value": "0.7"},
                    ],
                }],
            },
        },
        {"category": {"name": "IPTV"}, "service": {}},
        {
            "category": {"name": "FTTC"},
            "service": {
                "supportingService": [
                    {
                        "name": "VDSL_100",
                        "serviceCharacteristic": [
                            {"name": "maxPromisedSpeedDownload", "value": "104.81"},
                            {"name": "averagePromisedSpeedDownload", "value": "103.95"},
                        ],
                    },
                    {"name": "VDSL_50", "serviceCharacteristic": []},
                ],
            },
        },
    ]
}


def technologies(payload: dict[str, Any]) -> list[str]:
    return [o.technology for o in offers(payload)]


def test_a_promised_speed_arrives_as_a_string() -> None:
    assert mbps("103.95") == Decimal("103.95")
    assert mbps(None) is None
    assert mbps("") is None
    assert mbps("n/a") is None


def test_every_qualified_technology_is_read() -> None:
    assert technologies(ANSWER) == ["ADSL", "FWA", "VDSL", "VECT_VDSL"]


def test_a_hundred_over_copper_is_vectored() -> None:
    """Plain VDSL stops short of it, so the two rungs cannot share one code."""
    found = {o.technology: o for o in offers(ANSWER)}
    assert found["VECT_VDSL"].avg_down_mbps == Decimal("103.95")
    assert found["VDSL"].avg_down_mbps is None


def test_the_average_and_the_headline_are_both_kept() -> None:
    """The average is what the line carries; the maximum is what the advert says."""
    found = {o.technology: o for o in offers(ANSWER)}
    assert found["ADSL"].max_down_mbps == Decimal("15.22")
    assert found["ADSL"].avg_down_mbps == Decimal("11.24")
    assert found["ADSL"].avg_up_mbps == Decimal("0.7")


def test_wireless_qualifies_without_quoting_a_speed() -> None:
    """The answer is that it reaches here. The generation is never said, so none is claimed."""
    found = {o.technology: o for o in offers(ANSWER)}
    assert found["FWA"].max_down_mbps is None
    assert found["FWA"].avg_down_mbps is None


def test_a_category_that_is_not_broadband_is_dropped() -> None:
    """Their IPTV qualifies at the same address and is not an internet connection."""
    assert "IPTV" not in technologies(ANSWER)


def test_a_technology_we_do_not_know_is_dropped_not_guessed() -> None:
    """One they add later should be noticed, not absorbed under a code it does not fit."""
    payload = {"serviceQualificationItem": [{
        "category": {"name": "FTTH"},
        "service": {"supportingService": [{"name": "FTTH_2000", "serviceCharacteristic": []}]},
    }]}
    assert technologies(payload) == []


def test_an_answer_with_nothing_in_it_is_not_serviceable() -> None:
    assert read({"serviceQualificationItem": []}).serviceable is False
    assert read({}).serviceable is False


def test_the_cabinet_is_kept_because_copper_hangs_off_it() -> None:
    assert cabinet(ANSWER) == {"dslam": "447 - ΑΘΗΝΑΣ", "kvid": "0174"}
    assert cabinet({}) == {}


def test_the_request_carries_the_coordinates_and_nothing_else() -> None:
    """No crosswalk: the register placed the address and the point is the whole query."""
    target = Target(
        address_id=42, lat=37.9755648, lon=23.7348324,
        street="ΚΥΡΙΑΚΟΥ ΚΟΥΜΠΑΡΗ", street_no="1", municipality="ΔΗΜΟΣ ΑΘΗΝΑΙΩΝ",
    )
    body = Vodafone().request(target)
    criteria = body["data"]["searchCriteria"]  # type: ignore[index]
    place = criteria["service"]["place"][0]
    assert place["geographicLocation"]["bbox"] == [37.9755648, 23.7348324]
    assert body["requestId"] == "speedmap-42"
