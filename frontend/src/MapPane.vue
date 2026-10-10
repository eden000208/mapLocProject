<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from "vue";
import L from "leaflet";
import { LocateFixed } from "lucide-vue-next";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import "leaflet.markercluster";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import { api, errorText } from "./api";
import type { Cell } from "./types";
const props = defineProps<{ config: any }>();
const emit = defineEmits<{ selected: [Cell[]]; error: [string] }>();
const el = ref<HTMLElement>(),
  q = ref(""),
  tileFailed = ref(false),
  locating = ref(false),
  locationMessage = ref(""),
  mapState = ref("");
let map: L.Map, cluster: L.MarkerClusterGroup;
let sequence = 0;
let disposed = false;
let locationMarker: L.CircleMarker | undefined;
let accuracyCircle: L.Circle | undefined;
let locationRequest = 0;
// 仅在用户点击时请求定位；不持久化位置，视口加载沿用普通地图请求。
function currentLocation() {
  if (locating.value) return;
  if (!window.isSecureContext) {
    locationMessage.value =
      "定位需要 HTTPS 或 localhost 安全环境，请使用安全地址访问。";
    return;
  }
  if (!navigator.geolocation) {
    locationMessage.value = "当前浏览器不支持定位。";
    return;
  }
  locating.value = true;
  locationMessage.value = "正在获取当前位置…";
  const request = ++locationRequest;
  navigator.geolocation.getCurrentPosition(
    (position) => {
      if (disposed || request !== locationRequest) return;
      locating.value = false;
      const { latitude, longitude, accuracy } = position.coords;
      locationMarker?.remove();
      accuracyCircle?.remove();
      // 定位精度为估计半径；定位图形不参与基站选择。
      accuracyCircle = L.circle([latitude, longitude], {
        radius: accuracy,
        color: "#1677ff",
        fillOpacity: 0.08,
        interactive: false,
        pmIgnore: true,
      } as L.CircleOptions).addTo(map);
      locationMarker = L.circleMarker([latitude, longitude], {
        radius: 8,
        color: "#fff",
        weight: 3,
        fillColor: "#1677ff",
        fillOpacity: 1,
        interactive: false,
        pmIgnore: true,
      } as L.CircleMarkerOptions).addTo(map);
      map.setView([latitude, longitude], Math.max(map.getZoom(), 15));
      locationMessage.value =
        "定位成功，估计精度 ±" + Math.round(accuracy) + " 米";
    },
    (error) => {
      if (disposed || request !== locationRequest) return;
      locating.value = false;
      locationMessage.value =
        error.code === 1
          ? "定位权限被拒绝，请在浏览器站点设置中允许位置访问。"
          : error.code === 3
            ? "定位超时，请移动至信号较好的位置后重试。"
            : "暂时无法获取位置，请检查设备位置服务后重试。";
    },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
  );
}
function updateMapState() {
  const c = map.getCenter();
  mapState.value =
    "中心 " +
    c.lng.toFixed(5) +
    ", " +
    c.lat.toFixed(5) +
    " · 缩放 " +
    map.getZoom();
}
function tiles() {
  return `https://t{s}.tianditu.gov.cn/vec_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=vec&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk=${props.config.tianditu_key}`;
}
async function load() {
  const id = ++sequence;
  try {
    const b = map.getBounds();
    const r = await api.get("/stations", {
      params: {
        bbox: [
          Math.max(-180, b.getWest()),
          Math.max(-90, b.getSouth()),
          Math.min(180, b.getEast()),
          Math.min(90, b.getNorth()),
        ].join(","),
        zoom: map.getZoom(),
      },
    });
    if (disposed || id !== sequence) return;
    cluster.clearLayers();
    for (const s of r.data.items) {
      if (s.kind === "cluster") {
        const icon = L.divIcon({
          className: "cluster-pin",
          html: String(s.count),
          iconSize: [40, 40],
        });
        L.marker([s.lat, s.lng], { icon })
          .on("click", () => {
            if (s.bbox)
              map.fitBounds([
                [s.bbox[1], s.bbox[0]],
                [s.bbox[3], s.bbox[2]],
              ]);
            else map.setView([s.lat, s.lng], map.getZoom() + 2);
          })
          .addTo(cluster);
      } else {
        const m = L.circleMarker([s.lat, s.lng], {
          radius: 6,
          color: "#1677ff",
          fillOpacity: 0.8,
        });
        const tooltip = document.createElement("span");
        tooltip.textContent = s.station_name || "未命名站点";
        m.bindTooltip(tooltip);
        m.on("click", () => emit("selected", s.cells));
        cluster.addLayer(m);
      }
    }
  } catch (e) {
    emit("error", errorText(e));
  }
}
type Place = { name: string; address: string; lng: number; lat: number };
const places = ref<Place[]>([]),
  searching = ref(false),
  searchMessage = ref("");
let searchRequest = 0;
let searchController: AbortController | undefined;
let placeMarker: L.CircleMarker | undefined;
function showPlace(place: Place) {
  placeMarker?.remove();
  const label = document.createElement("span");
  label.textContent = place.name + " · " + place.address;
  placeMarker = L.circleMarker([place.lat, place.lng], {
    radius: 10,
    color: "#e66b22",
    fillOpacity: 0.7,
    pmIgnore: true,
  } as L.CircleMarkerOptions)
    .bindTooltip(label)
    .addTo(map);
  map.setView([place.lat, place.lng], 16);
}
async function locate() {
  const keyword = q.value.trim();
  ++searchRequest;
  searchController?.abort();
  searching.value = false;
  places.value = [];
  if (!keyword || keyword.length > 100) {
    searchMessage.value =
      "请输入 1～100 个字符的地名、地址或场所名称，例如：荆门市政府。";
    return;
  }
  if (!props.config.tianditu_key) {
    searchMessage.value = "尚未配置天地图密钥，无法搜索地点。";
    return;
  }
  const id = searchRequest;
  const controller = new AbortController();
  searchController = controller;
  const timer = window.setTimeout(() => controller.abort(), 15000);
  searching.value = true;
  searchMessage.value = "正在搜索地点…";
  try {
    const b = map.getBounds();
    const params = new URLSearchParams({
      type: "query",
      tk: props.config.tianditu_key,
      postStr: JSON.stringify({
        keyWord: keyword,
        level: map.getZoom(),
        mapBound: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(
          ",",
        ),
        queryType: 1,
        start: 0,
        count: 10,
      }),
    });
    // 地点搜索直接调用天地图；搜索词不用于过滤基站。
    const response = await fetch(
      "https://api.tianditu.gov.cn/v2/search?" + params,
      { signal: controller.signal },
    );
    if (!response.ok) throw new Error("network");
    const data = await response.json();
    if (disposed || id !== searchRequest) return;
    if (data.status && String(data.status.infocode) !== "1000") {
      searchMessage.value =
        "天地图地点搜索未成功，请检查密钥是否开通搜索服务及网页域名权限。";
      return;
    }
    const candidates = [
      ...(data.pois || []),
      ...(data.area ? [data.area] : []),
    ];
    places.value = candidates.flatMap((p: any) => {
      const [lng, lat] = String(p.lonlat || "")
        .split(",")
        .map(Number);
      return Number.isFinite(lng) &&
        Number.isFinite(lat) &&
        Math.abs(lng) <= 180 &&
        Math.abs(lat) <= 90
        ? [
            {
              name: String(p.name || keyword),
              address: String(p.address || ""),
              lng,
              lat,
            },
          ]
        : [];
    });
    searchMessage.value = places.value.length
      ? "点击结果定位；可输入城市名缩小搜索范围。"
      : "未找到地点，请补充城市、街道或更完整的场所名称。";
    if (places.value[0]) showPlace(places.value[0]);
  } catch {
    if (!disposed && id === searchRequest)
      searchMessage.value = controller.signal.aborted
        ? "地点搜索超时，请重试。"
        : "无法连接天地图搜索，请检查网络及密钥的搜索服务权限。";
  } finally {
    window.clearTimeout(timer);
    if (id === searchRequest) searching.value = false;
  }
}
onMounted(() => {
  map = L.map(el.value!, { maxZoom: 18 }).setView(
    [props.config.map_center[1], props.config.map_center[0]],
    props.config.map_zoom,
  );
  if (props.config.tianditu_key) {
    L.tileLayer(tiles(), {
      subdomains: "01234567",
      maxZoom: 18,
      attribution: "天地图",
    })
      .on("tileerror", () => (tileFailed.value = true))
      .addTo(map);
    L.tileLayer(
      tiles().replace("/vec_w/", "/cva_w/").replace("LAYER=vec", "LAYER=cva"),
      { subdomains: "01234567", maxZoom: 18, attribution: "天地图注记" },
    )
      .on("tileerror", () => (tileFailed.value = true))
      .addTo(map);
  }
  cluster = L.markerClusterGroup().addTo(map);
  map.pm.setLang("zh");
  map.pm.addControls({
    position: "topleft",
    drawMarker: false,
    drawCircleMarker: false,
    drawPolyline: false,
    drawText: false,
    editMode: false,
    dragMode: false,
    cutPolygon: false,
    removalMode: true,
    rotateMode: false,
  });
  map.on("pm:create", async (e: any) => {
    if (map.getZoom() < (props.config.min_draw_zoom || 12)) {
      map.removeLayer(e.layer);
      emit("error", `请放大至 ${props.config.min_draw_zoom || 12} 级再圈选`);
      return;
    }
    try {
      const circle = e.shape === "Circle";
      const c = circle ? e.layer.getLatLng() : null;
      const r = await api.post(
        "/selections/resolve",
        circle
          ? {
              type: "circle",
              center: [c.lng, c.lat],
              radius: e.layer.getRadius(),
            }
          : {
              type: e.shape === "Rectangle" ? "rect" : "polygon",
              geometry: e.layer.toGeoJSON().geometry,
            },
      );
      if (!disposed) emit("selected", r.data.cells);
    } catch (err) {
      emit("error", errorText(err));
    }
  });
  map.on("moveend", () => {
    updateMapState();
    load();
  });
  updateMapState();
  load();
});
onBeforeUnmount(() => {
  disposed = true;
  locationRequest++;
  searchRequest++;
  searchController?.abort();
  map?.remove();
});
</script>
<template>
  <div class="map-shell">
    <div ref="el" class="map-canvas"></div>
    <div class="location-tools">
      <button
        :disabled="locating"
        title="获取当前位置"
        @click="currentLocation"
      >
        <LocateFixed :size="16" aria-hidden="true" />
        {{ locating ? "正在定位…" : "当前定位" }}
      </button>
      <p v-if="locationMessage" role="status">{{ locationMessage }}</p>
    </div>
    <div class="map-state">{{ mapState }}</div>
    <div v-if="!config.tianditu_key" class="map-key-hint" role="status">
      未配置天地图 Key，底图暂不可用。请在 .env 中配置
      TIANDITU_KEY；仍可加载站点并圈选。
    </div>
    <div
      v-if="config.tianditu_key && tileFailed"
      class="map-key-hint"
      role="status"
    >
      底图加载失败，请检查天地图 Key 的 Web 权限及网络；仍可加载站点并圈选。
    </div>
    <div class="map-search">
      <input
        v-model="q"
        placeholder="搜索地名、地址、学校、医院等"
        maxlength="100"
        aria-label="地点搜索（1～100 个字符）"
        @keyup.enter="locate"
      /><button :disabled="searching" @click="locate">
        {{ searching ? "搜索中…" : "搜索" }}
      </button>
      <div class="place-results">
        <p role="status">
          {{ searchMessage || "输入 1～100 个字符，例如：荆门市政府" }}
        </p>
        <button v-for="(p, i) in places" :key="i" @click="showPlace(p)">
          <b>{{ p.name }}</b
          ><small>{{ p.address || "点击查看位置" }}</small>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.map-key-hint {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 800;
  max-width: 80%;
  padding: 12px 18px;
  border: 1px solid #e5d5ae;
  border-radius: 6px;
  background: #fffaf0;
  color: #805a15;
  box-shadow: 0 2px 8px #0001;
  font-size: 13px;
  line-height: 1.6;
}
.location-tools {
  position: absolute;
  right: 14px;
  bottom: 40px;
  z-index: 800;
  text-align: right;
  max-width: 330px;
}
.location-tools p {
  padding: 9px 12px;
  background: #fff;
  border: 1px solid #d8e4f4;
  border-radius: 5px;
  font-size: 12px;
  line-height: 1.6;
  color: #52647b;
}
.location-tools button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.map-state {
  position: absolute;
  bottom: 0;
  left: 0;
  z-index: 800;
  background: #ffffffdf;
  padding: 4px 10px;
  font-size: 11px;
  color: #52647b;
  pointer-events: none;
}
</style>

<style scoped>
.map-search {
  flex-wrap: wrap;
  width: 330px;
  background: white;
  padding: 8px;
  border-radius: 6px;
}
.place-results {
  width: 100%;
  max-height: 260px;
  overflow-y: auto;
}
.place-results p {
  margin: 4px 0;
  font-size: 12px;
  color: #52647b;
}
.place-results button {
  display: block;
  width: 100%;
  text-align: left;
  margin-top: 4px;
}
.place-results small {
  display: block;
  color: #52647b;
  margin-top: 4px;
}
</style>
