import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const MUMBAI_CENTER = [19.076, 72.8777];

function emojiDivIcon(emoji, { size = 26, className = "" } = {}) {
  return L.divIcon({
    html: `<div style="font-size:${size}px;line-height:1;transform:translate(-50%,-50%);filter:drop-shadow(0 1px 2px rgba(0,0,0,.5))">${emoji}</div>`,
    className: `rqm-emoji-icon ${className}`,
    iconSize: [0, 0],
  });
}

function ambulanceDivIcon() {
  return L.divIcon({
    html: `<div class="rqm-amb-rot" style="font-size:24px;line-height:1;transform:translate(-50%,-50%) rotate(0deg);filter:drop-shadow(0 1px 3px rgba(0,0,0,.6))">🚑</div>`,
    className: "rqm-emoji-icon",
    iconSize: [0, 0],
  });
}

const trafficColor = { GREEN: "#3fb950", YELLOW: "#e0c62c", ORANGE: "#e08a2c", RED: "#e5484d" };

export default function LiveSimulationMap({ snapshot, height = 560 }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const layersRef = useRef({});

  // --- init map once ---
  useEffect(() => {
    if (mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: MUMBAI_CENTER,
      zoom: 12,
      zoomControl: true,
      attributionControl: true,
    });
    L.tileLayer(TILE_URL, {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    const legend = L.control({ position: "bottomright" });
    legend.onAdd = () => {
      const div = L.DomUtil.create("div", "rqm-map-legend");
      div.innerHTML = `
        <div style="font-weight:700;margin-bottom:6px;letter-spacing:.04em;">LEGEND</div>
        <div>🚑 Active ambulance</div>
        <div>🚨 Incident</div>
        <div>🏥 Hospital</div>
        <div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#4ea1ff;margin-right:6px;"></span>Other available units</div>
        <div><span style="display:inline-block;width:18px;height:3px;background:#4ea1ff;margin-right:4px;vertical-align:middle;"></span>Active route</div>
        <div><span style="display:inline-block;width:18px;height:3px;border-top:3px dashed #e0c62c;margin-right:4px;vertical-align:middle;"></span>Alternative / rerouted</div>
        <div><span style="display:inline-block;width:18px;height:3px;background:#e5484d;margin-right:4px;vertical-align:middle;"></span>Blocked segment</div>
        <div style="opacity:.65;">Dotted circle = GPS uncertainty</div>
      `;
      return div;
    };
    legend.addTo(map);

    mapRef.current = map;
    layersRef.current = {};

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // --- reflect snapshot onto layers ---
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const layers = layersRef.current;

    // Incident marker
    if (snapshot.incident) {
      const pos = [snapshot.incident.lat, snapshot.incident.lon];
      if (!layers.incident) {
        layers.incident = L.marker(pos, { icon: emojiDivIcon("🚨", { size: 26, className: "rqm-pulse-icon" }), zIndexOffset: 500 })
          .addTo(map)
          .bindTooltip(`${snapshot.incident.label} (${snapshot.incident.severity.toUpperCase()})`);
        map.setView(pos, 13);
      } else {
        layers.incident.setLatLng(pos);
      }
    }

    // Hospital marker (selected destination) -- highlighted
    if (snapshot.hospital) {
      const pos = [snapshot.hospital.lat, snapshot.hospital.lon];
      if (!layers.hospitalKey || layers.hospitalKey !== snapshot.hospital.id) {
        if (layers.hospital) map.removeLayer(layers.hospital);
        layers.hospital = L.marker(pos, { icon: emojiDivIcon("🏥", { size: 26 }), zIndexOffset: 400 })
          .addTo(map)
          .bindTooltip(snapshot.hospital.name);
        layers.hospitalKey = snapshot.hospital.id;
      }
      if (layers.hospital) {
        const stale = snapshot.hospital.stale;
        layers.hospital.setTooltipContent(
          `${snapshot.hospital.name}${stale ? " -- CAPACITY DATA STALE" : ""} (${snapshot.hospital.availableBeds} beds avail.)`
        );
      }
    }

    // Other fleet ambulances (context only, real fetched positions)
    if (snapshot.fleet && snapshot.fleet.length) {
      if (!layers.fleetGroup) {
        layers.fleetGroup = L.layerGroup().addTo(map);
      }
      if (layers.fleetCount !== snapshot.fleet.length) {
        layers.fleetGroup.clearLayers();
        snapshot.fleet.forEach((a) => {
          L.circleMarker([a.lat, a.lon], {
            radius: 4,
            color: "#4ea1ff",
            fillColor: "#4ea1ff",
            fillOpacity: 0.85,
            weight: 1,
          })
            .addTo(layers.fleetGroup)
            .bindTooltip(`${a.id} (${a.type}) - AVAILABLE`);
        });
        layers.fleetCount = snapshot.fleet.length;
      }
    }

    // Active ambulance marker + heading rotation
    if (snapshot.ambulance && snapshot.ambulance.position) {
      const [lon, lat] = snapshot.ambulance.position;
      if (!layers.ambulance) {
        layers.ambulance = L.marker([lat, lon], { icon: ambulanceDivIcon(), zIndexOffset: 1000 }).addTo(map);
      } else {
        layers.ambulance.setLatLng([lat, lon]);
      }
      layers.ambulance.bindTooltip(`${snapshot.ambulance.id} - ${snapshot.ambulance.speedKph.toFixed(0)} km/h`, { permanent: false });
      const el = layers.ambulance.getElement();
      if (el) {
        const inner = el.querySelector(".rqm-amb-rot");
        if (inner) inner.style.transform = `translate(-50%,-50%) rotate(${snapshot.ambulance.headingDeg}deg)`;
      }
    }

    // GPS uncertainty circle (around reported position)
    if (snapshot.gps && snapshot.gps.reported) {
      const [lon, lat] = snapshot.gps.reported;
      if (!layers.gpsCircle) {
        layers.gpsCircle = L.circle([lat, lon], {
          radius: snapshot.gps.accuracyM || 10,
          color: "#4ea1ff",
          weight: 1,
          dashArray: "3 4",
          fillOpacity: 0.08,
        }).addTo(map);
      } else {
        layers.gpsCircle.setLatLng([lat, lon]);
        layers.gpsCircle.setRadius(snapshot.gps.accuracyM || 10);
      }
    }

    // Traveled trail
    if (snapshot.ambulance && snapshot.ambulance.traveledTrail && snapshot.ambulance.traveledTrail.length > 1) {
      const latlngs = snapshot.ambulance.traveledTrail.map(([lo, la]) => [la, lo]);
      if (!layers.trail) {
        layers.trail = L.polyline(latlngs, { color: "#5c6c7a", weight: 3, opacity: 0.6 }).addTo(map);
      } else {
        layers.trail.setLatLngs(latlngs);
      }
    }

    // Active route polyline (recolor by traffic level)
    if (snapshot.route && snapshot.route.coordinates) {
      const color = trafficColor[snapshot.traffic?.level] || "#4ea1ff";
      const latlngs = snapshot.route.coordinates.map(([lo, la]) => [la, lo]);
      if (layers.routeCoordsRef !== snapshot.route.coordinates) {
        if (layers.route) map.removeLayer(layers.route);
        layers.route = L.polyline(latlngs, { color, weight: 5, opacity: 0.85 }).addTo(map);
        layers.routeCoordsRef = snapshot.route.coordinates;
      } else if (layers.route) {
        layers.route.setStyle({ color });
      }
    }

    // Failed segment highlight
    if (snapshot.route && snapshot.route.failedSegment) {
      const { a, b } = snapshot.route.failedSegment;
      const latlngs = [
        [a[1], a[0]],
        [b[1], b[0]],
      ];
      if (!layers.failedSegment) {
        layers.failedSegment = L.polyline(latlngs, { color: "#e5484d", weight: 7, opacity: 0.95, dashArray: "2 6" }).addTo(map);
      } else {
        layers.failedSegment.setLatLngs(latlngs);
      }
    } else if (layers.failedSegment) {
      map.removeLayer(layers.failedSegment);
      layers.failedSegment = null;
    }
  }, [snapshot]);

  return <div ref={containerRef} style={{ height, width: "100%", borderRadius: 10, overflow: "hidden" }} />;
}
