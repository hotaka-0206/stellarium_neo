"""Screen-fixed JPL Horizons text overlay in Stellarium.

Only this module owns the five screen labels it creates. It does not modify
JPL ephemeris calculation or Stellarium's object/marker selection.
"""

from datetime import datetime, timezone
import json
import logging

from observer import ObserverLocation
from stellarium_service import (
    degrees_to_dec_text,
    degrees_to_ra_text,
    run_stellarium_script,
    StellariumApiError,
)

_LOG = logging.getLogger(__name__)
_OVERLAY_KEY = "__stellariumNeoJplInfoOverlayIds"


def build_jpl_info_overlay_script(
    name: str,
    ra_deg: float,
    dec_deg: float,
    datetime_utc: datetime,
    observer: ObserverLocation,
) -> str:
    """Generate text updates; never destroy/recreate labels on a regular tick."""
    if datetime_utc.tzinfo is None:
        raise ValueError("情報表示時刻にはタイムゾーンが必要です。")

    date = datetime_utc.astimezone(timezone.utc)
    utc_text = date.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    display_name = name.strip() or "Unnamed target"
    if len(display_name) > 60:
        display_name = display_name[:57] + "..."

    rows = [
        f"{display_name}  |  JPL Horizons",
        f"RA: {degrees_to_ra_text(ra_deg)}  ({ra_deg:.8f} deg)",
        f"Dec: {degrees_to_dec_text(dec_deg)}  ({dec_deg:.8f} deg)",
        f"UTC: {utc_text}",
        (f"Site: {observer.name}  "
         f"({observer.latitude_deg:.5f}, {observer.longitude_deg:.5f}, "
         f"{observer.altitude_m:.1f} m)"),
        "Coordinates: ICRF / airless apparent",
    ]
    rows_json = json.dumps(rows, ensure_ascii=False)
    key = _OVERLAY_KEY
    return "\n".join([
        "var neoInfoRoot = (typeof globalThis !== 'undefined') ? globalThis : this;",
        f"var neoInfoRows = {rows_json};",
        f"var neoInfoIds = neoInfoRoot.{key};",
        "if (!neoInfoIds || neoInfoIds.length !== neoInfoRows.length) {",
        "  if (neoInfoIds) {",
        "    for (var j = 0; j < neoInfoIds.length; ++j) {",
        "      if (neoInfoIds[j] > 0) LabelMgr.deleteLabel(neoInfoIds[j]);",
        "    }",
        "  }",
        "  neoInfoIds = [];",
        "  for (var i = 0; i < neoInfoRows.length; ++i) {",
        "    var infoId = LabelMgr.labelScreen(",
        "      neoInfoRows[i], 24, 92 + 24 * i, true,",
        "      i === 0 ? 16 : 13, i === 0 ? '#9bcaff' : '#ffffff',",
        "      false, 0);",
        "    if (infoId <= 0) {",
        "      for (var k = 0; k < neoInfoIds.length; ++k) {",
        "        LabelMgr.deleteLabel(neoInfoIds[k]);",
        "      }",
        "      throw new Error('JPL info screen label creation failed');",
        "    }",
        "    neoInfoIds.push(infoId);",
        "  }",
        f"  neoInfoRoot.{key} = neoInfoIds;",
        "} else {",
        "  for (var m = 0; m < neoInfoRows.length; ++m) {",
        "    LabelMgr.setLabelText(neoInfoIds[m], neoInfoRows[m]);",
        "  }",
        "}",
    ])


def build_clear_jpl_info_overlay_script() -> str:
    key = _OVERLAY_KEY
    return "\n".join([
        "var neoInfoRoot = (typeof globalThis !== 'undefined') ? globalThis : this;",
        f"var neoInfoIds = neoInfoRoot.{key};",
        "if (neoInfoIds) {",
        "  for (var i = 0; i < neoInfoIds.length; ++i) {",
        "    if (neoInfoIds[i] > 0) LabelMgr.deleteLabel(neoInfoIds[i]);",
        "  }",
        f"  neoInfoRoot.{key} = null;",
        "}",
    ])


def show_jpl_info_overlay(
    name: str,
    ra_deg: float,
    dec_deg: float,
    datetime_utc: datetime,
    observer: ObserverLocation,
) -> None:
    try:
        run_stellarium_script(build_jpl_info_overlay_script(
            name, ra_deg, dec_deg, datetime_utc, observer,
        ))
    except StellariumApiError as error:
        # Never interrupt RA/Dec tracking if an optional text overlay fails.
        _LOG.warning("JPL information overlay failed: %s", error)


def clear_jpl_info_overlay() -> None:
    try:
        run_stellarium_script(build_clear_jpl_info_overlay_script())
    except StellariumApiError as error:
        _LOG.warning("JPL information overlay cleanup failed: %s", error)
