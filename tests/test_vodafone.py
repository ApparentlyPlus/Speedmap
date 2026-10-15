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

# as their endpoint answers, FWA qualified with no service at all
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


def _techs(payload: dict[str, Any]) -> list[str]:
    return [o.technology for o in offers(payload)]


def test_mbps() -> None:
    assert mbps("103.95") == Decimal("103.95")
    assert mbps(None) is None
    assert mbps("") is None
    assert mbps("n/a") is None


def test_offers() -> None:
    assert _techs(ANSWER) == ["ADSL", "FWA", "VDSL", "VECT_VDSL"]
    assert "IPTV" not in _techs(ANSWER)

    found = {o.technology: o for o in offers(ANSWER)}
    # 100 over copper is vectored
    assert found["VECT_VDSL"].avg_down_mbps == Decimal("103.95")
    assert found["VDSL"].avg_down_mbps is None
    assert found["ADSL"].max_down_mbps == Decimal("15.22")
    assert found["ADSL"].avg_down_mbps == Decimal("11.24")
    assert found["ADSL"].avg_up_mbps == Decimal("0.7")
    assert found["FWA"].max_down_mbps is None
    assert found["FWA"].avg_down_mbps is None

    # unknown, so dropped rather than guessed
    payload = {"serviceQualificationItem": [{
        "category": {"name": "FTTH"},
        "service": {"supportingService": [{"name": "FTTH_2000", "serviceCharacteristic": []}]},
    }]}
    assert _techs(payload) == []


def test_read() -> None:
    assert read({"serviceQualificationItem": []}).serviceable is False
    assert read({}).serviceable is False
    assert cabinet(ANSWER) == {"dslam": "447 - ΑΘΗΝΑΣ", "kvid": "0174"}
    assert cabinet({}) == {}


def test_request() -> None:
    target = Target(address_id=42, lat=37.9755648, lon=23.7348324, street="ΚΥΡΙΑΚΟΥ ΚΟΥΜΠΑΡΗ", street_no="1",
                    municipality="ΔΗΜΟΣ ΑΘΗΝΑΙΩΝ")
    body = Vodafone().request(target)
    criteria = body["data"]["searchCriteria"]  # type: ignore[index]
    place = criteria["service"]["place"][0]
    assert place["geographicLocation"]["bbox"] == [37.9755648, 23.7348324]
    assert body["requestId"] == "speedmap-42"
