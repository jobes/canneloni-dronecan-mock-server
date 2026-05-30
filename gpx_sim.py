import math
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

from geo_utils import calculate_bearing, calculate_haversine_distance


@dataclass
class GPXPoint:
    """
    Represents a single track point from a GPX file
    along with precomputed navigation parameters.
    """
    lat: float
    lon: float
    ele: float
    time: datetime
    elapsed_sec: float = 0.0
    
    # Precomputed navigation values relative to the next point
    bearing: float = 0.0
    speed: float = 0.0
    v_n: float = 0.0  # Velocity North (m/s)
    v_e: float = 0.0  # Velocity East (m/s)
    v_d: float = 0.0  # Velocity Down (m/s)


class GPXSimulator:
    """
    Loads a GPX file and simulates real-time playback by tracking
    elapsed seconds and returning the corresponding active GPX point.
    """
    def __init__(self, gpx_path: str) -> None:
        self.gpx_path: str = gpx_path
        self.points: list[GPXPoint] = []
        self.total_duration: float = 0.0
        self._load_gpx()

    def _load_gpx(self) -> None:
        """Parses the GPX file and precomputes speeds, bearings, and velocities."""
        namespaces = {'gpx': 'http://www.topografix.com/GPX/1/1'}
        try:
            tree = ET.parse(self.gpx_path)
            root = tree.getroot()
        except Exception as e:
            logger.error(f"Error parsing GPX file {self.gpx_path}: {e}")
            raise e

        # 1. Parse all GPX trackpoints
        raw_points: list[GPXPoint] = []
        for trkpt in root.findall('.//gpx:trkpt', namespaces):
            lat = float(trkpt.attrib['lat'])
            lon = float(trkpt.attrib['lon'])
            
            ele_elem = trkpt.find('gpx:ele', namespaces)
            ele = float(ele_elem.text) if ele_elem is not None and ele_elem.text is not None else 0.0
            
            time_elem = trkpt.find('gpx:time', namespaces)
            if time_elem is not None and time_elem.text is not None:
                # Replace 'Z' with UTC timezone offset to ensure compatibility
                t_str = time_elem.text.replace('Z', '+00:00')
                time_dt = datetime.fromisoformat(t_str)
            else:
                time_dt = datetime.now()
            
            raw_points.append(GPXPoint(lat=lat, lon=lon, ele=ele, time=time_dt))

        if not raw_points:
            raise ValueError(f"No trackpoints found in GPX file: {self.gpx_path}")

        # 2. Sort chronologically and compute elapsed offsets from startup
        raw_points.sort(key=lambda p: p.time)
        start_time = raw_points[0].time
        for point in raw_points:
            point.elapsed_sec = (point.time - start_time).total_seconds()

        # 3. Precompute navigation metrics between consecutive points
        n = len(raw_points)
        for i in range(n - 1):
            p1 = raw_points[i]
            p2 = raw_points[i + 1]
            
            dt = p2.elapsed_sec - p1.elapsed_sec
            if dt > 0:
                distance_m = calculate_haversine_distance(p1.lat, p1.lon, p2.lat, p2.lon)
                p1.bearing = calculate_bearing(p1.lat, p1.lon, p2.lat, p2.lon)
                p1.speed = distance_m / dt
                
                # Convert polar coordinates (speed, bearing) to Cartesian NED velocities
                p1.v_n = p1.speed * math.cos(math.radians(p1.bearing))
                p1.v_e = p1.speed * math.sin(math.radians(p1.bearing))
                p1.v_d = -(p2.ele - p1.ele) / dt  # Negative down is upwards
            else:
                # Fallback: if times match, reuse the preceding point's calculations
                if i > 0:
                    prev = raw_points[i - 1]
                    p1.bearing, p1.speed = prev.bearing, prev.speed
                    p1.v_n, p1.v_e, p1.v_d = prev.v_n, prev.v_e, prev.v_d

        # 4. Propagate final point's velocity to prevent sudden stops at loop boundaries
        if n > 1:
            last = raw_points[-1]
            prev = raw_points[-2]
            last.bearing, last.speed = prev.bearing, prev.speed
            last.v_n, last.v_e, last.v_d = prev.v_n, prev.v_e, prev.v_d

        self.points = raw_points
        self.total_duration = self.points[-1].elapsed_sec
        logger.info(f"Loaded {len(self.points)} GPX points. Total track duration: {self.total_duration} seconds.")

    def get_active_point(self, elapsed_sec: float) -> GPXPoint | None:
        """
        Returns the GPXPoint active at the given elapsed simulation time.
        Preserves original timestamp gaps. If elapsed_sec exceeds the track length,
        it wraps around to enable infinite looping.
        """
        if not self.points:
            return None
        
        # Wrap time if looping
        wrapped_time = elapsed_sec % self.total_duration if self.total_duration > 0 else 0.0

        # Scan for the active point matching the current elapsed timeframe
        active_point = self.points[0]
        for point in self.points:
            if point.elapsed_sec <= wrapped_time:
                active_point = point
            else:
                break
        
        return active_point
