from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ObserverLocation:
    latitude_deg: float
    longitude_deg: float
    altitude_m: float = 0.0
    name: str = "Custom observer"

    def __post_init__(self) -> None:
        values = {
            "緯度": self.latitude_deg,
            "経度": self.longitude_deg,
            "標高": self.altitude_m,
        }

        for label, value in values.items():
            if not math.isfinite(value):
                raise ValueError(f"{label}は有限の数値で指定してください。")

        if not -90.0 <= self.latitude_deg <= 90.0:
            raise ValueError("緯度は -90～90 度で指定してください。")

        if not -180.0 <= self.longitude_deg <= 180.0:
            raise ValueError("経度は -180～180 度で指定してください。")

        if not self.name.strip():
            raise ValueError("観測地点名が空です。")

    @property
    def altitude_km(self) -> float:
        return self.altitude_m / 1000.0

    def to_horizons_site_coord(self) -> str:
        return (
            f"{self.longitude_deg:.10f},"
            f"{self.latitude_deg:.10f},"
            f"{self.altitude_km:.6f}"
        )
