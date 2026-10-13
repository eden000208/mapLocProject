<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from "vue";
import L from "leaflet";
import {
  LocateFixed,
  Search,
  Square,
  Pentagon,
  Circle,
  Trash2,
  Plus,
  Minus,
  Compass,
  MapPin,
  X,
  MousePointer2,
} from "lucide-vue-next";
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
  mapState = ref(""),
  stationCount = ref(0),
  drawMode = ref("");
let map: L.Map, cluster: L.MarkerClusterGroup;
let sequence = 0;
let disposed = false;
let locationMarker: L.CircleMarker | undefined;
let accuracyCircle: L.Circle | undefined;
let locationRequest = 0;
let resizeObserver: ResizeObserver | undefined;
let resizeFrame = 0;
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
        color: "#5b7c8b",
        fillOpacity: 0.08,
        interactive: false,
        pmIgnore: true,
      } as L.CircleOptions).addTo(map);
      locationMarker = L.circleMarker([latitude, longitude], {
        radius: 8,
        color: "#fff",
        weight: 3,
        fillColor: "#5b7c8b",
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
          color: "#4f6a53",
          fillColor: "#78906b",
          weight: 2,
          fillOpacity: 0.8,
          pmIgnore: true,
        } as L.CircleMarkerOptions);
        const tooltip = document.createElement("span");
        tooltip.textContent = s.station_name || "未命名站点";
        m.bindTooltip(tooltip);
        m.on("click", () => emit("selected", s.cells));
        cluster.addLayer(m);
      }
    }
    stationCount.value = r.data.items.reduce(
      (count: number, s: any) => count + (s.kind === "cluster" ? s.count : 1),
      0,
    );
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
    color: "#b75b40",
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
    searchMessage.value = "地点搜索暂不可用，请联系管理员。";
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
function setDrawMode(mode: string) {
  const next = drawMode.value === mode ? "" : mode;
  map.pm.disableDraw();
  map.pm.disableGlobalRemovalMode();
  drawMode.value = next;
  if (next === "remove") map.pm.enableGlobalRemovalMode();
  else if (next) map.pm.enableDraw(next as "Rectangle" | "Polygon" | "Circle");
}
function resetView() {
  map.setView(
    [props.config.map_center[1], props.config.map_center[0]],
    props.config.map_zoom,
  );
}
onMounted(() => {
  map = L.map(el.value!, { maxZoom: 18, zoomControl: false }).setView(
    [props.config.map_center[1], props.config.map_center[0]],
    props.config.map_zoom,
  );
  // 监听实际容器变化，兼容窗口缩放、侧栏断点及字体尺寸变化。
  resizeObserver = new ResizeObserver(() => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => {
      if (!disposed) map.invalidateSize({ pan: false });
    });
  });
  resizeObserver.observe(el.value!);
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
  map.pm.setGlobalOptions({
    pathOptions: {
      color: "#b75b40",
      fillColor: "#b75b40",
      fillOpacity: 0.1,
      weight: 2,
    },
  });
  map.on("pm:drawend", () => {
    drawMode.value = "";
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
  resizeObserver?.disconnect();
  cancelAnimationFrame(resizeFrame);
  map?.remove();
});
</script>
<template>
  <div class="map-shell">
    <div ref="el" class="map-canvas" aria-label="基站选择地图"></div>
    <form class="map-search" @submit.prevent="locate">
      <div class="search-input-row">
        <Search :size="17" /><input
          v-model="q"
          placeholder="搜索地名、地址或场所"
          maxlength="100"
          aria-label="地点搜索（1～100 个字符）"
        /><button type="submit" :disabled="searching">
          {{ searching ? "搜索中…" : "搜索" }}
        </button>
      </div>
      <div v-if="searchMessage || places.length" class="place-results">
        <div class="search-result-heading">
          <p role="status">{{ searchMessage }}</p>
          <button
            type="button"
            aria-label="关闭搜索结果"
            @click="
              places = [];
              searchMessage = '';
            "
          >
            <X :size="14" />
          </button>
        </div>
        <button
          type="button"
          v-for="(p, i) in places"
          :key="i"
          @click="showPlace(p)"
        >
          <MapPin :size="15" /><span
            ><b>{{ p.name }}</b
            ><small>{{ p.address || "点击查看位置" }}</small></span
          >
        </button>
      </div>
    </form>
    <div class="draw-toolbar" role="group" aria-label="圈选工具">
      <button
        :class="{ active: !drawMode }"
        aria-label="点选"
        title="点选站点"
        :aria-pressed="!drawMode"
        @click="setDrawMode('')"
      >
        <MousePointer2 :size="16" /><span>点选</span></button
      ><span class="tool-divider"></span
      ><button
        v-for="tool in [
          { mode: 'Rectangle', label: '矩形', icon: Square },
          { mode: 'Polygon', label: '多边形', icon: Pentagon },
          { mode: 'Circle', label: '圆形', icon: Circle },
        ]"
        :key="tool.mode"
        :aria-label="tool.label"
        :title="tool.label + '圈选'"
        :class="{ active: drawMode === tool.mode }"
        :aria-pressed="drawMode === tool.mode"
        @click="setDrawMode(tool.mode)"
      >
        <component :is="tool.icon" :size="16" /><span>{{
          tool.label
        }}</span></button
      ><span class="tool-divider"></span
      ><button
        :class="{ active: drawMode === 'remove' }"
        aria-label="移除"
        title="移除圈选范围"
        :aria-pressed="drawMode === 'remove'"
        @click="setDrawMode('remove')"
      >
        <Trash2 :size="16" /><span>移除</span>
      </button>
    </div>
    <div class="map-guide">
      <span class="station-dot"></span
      ><span>视野内 {{ stationCount.toLocaleString() }} 个站点</span
      ><span class="guide-divider"></span
      ><span>{{
        drawMode === "remove"
          ? "点击图形移除圈选范围"
          : drawMode
            ? "在地图上绘制查询范围"
            : "点击站点添加小区"
      }}</span>
    </div>
    <div class="map-controls">
      <button
        :disabled="locating"
        title="获取当前位置"
        aria-label="获取当前位置"
        @click="currentLocation"
      >
        <LocateFixed :size="18" /></button
      ><button
        title="返回初始视野"
        aria-label="返回初始视野"
        @click="resetView"
      >
        <Compass :size="18" /></button
      ><span></span
      ><button title="放大" aria-label="放大地图" @click="map.zoomIn()">
        <Plus :size="18" /></button
      ><button title="缩小" aria-label="缩小地图" @click="map.zoomOut()">
        <Minus :size="18" />
      </button>
    </div>
    <div v-if="locationMessage" class="location-message" role="status">
      {{ locationMessage }}
    </div>
    <div class="map-state">{{ mapState }}</div>
    <div
      v-if="!config.tianditu_key || tileFailed"
      class="map-key-hint"
      role="status"
    >
      {{
        !config.tianditu_key
          ? "底图暂不可用，请联系管理员。仍可点选站点或圈选区域。"
          : "底图加载失败，请检查网络或联系管理员。仍可选择站点。"
      }}
    </div>
  </div>
</template>
<style scoped>
.map-shell {
  position: relative;
  min-width: 0;
  isolation: isolate;
  background: #eeede5;
}
.map-canvas {
  height: 100%;
  width: 100%;
  background: #eeede5;
  font-family: inherit;
}
.map-search {
  position: absolute;
  top: 1.2857rem;
  left: 1.2857rem;
  z-index: 800;
  width: min(27.1429rem, calc(100% - 2.5714rem));
  border: 1px solid var(--line);
  border-radius: 0.6429rem;
  background: var(--surface);
  box-shadow: var(--shadow);
}
.search-input-row {
  display: flex;
  align-items: center;
  padding: 0.4286rem 0.5rem 0.4286rem 0.9286rem;
  gap: 0.6429rem;
}
.search-input-row > svg {
  color: var(--muted);
  flex-shrink: 0;
}
.search-input-row input {
  flex: 1;
  width: 100%;
  border: 0;
  background: transparent;
  font-size: 0.8571rem;
  padding: 0.5714rem 0;
}
.search-input-row button {
  min-height: 2.2143rem;
  font-size: 0.8571rem;
  padding: 0.4286rem 0.7857rem;
  background: var(--sidebar);
  border: 0;
  white-space: nowrap;
}
.place-results {
  border-top: 1px solid var(--line);
  padding: 0.7143rem;
  max-height: 19.2857rem;
  overflow: auto;
}
.search-result-heading {
  display: flex;
  align-items: flex-start;
  gap: 0.5714rem;
}
.search-result-heading p {
  flex: 1;
  font-size: 0.8571rem;
  color: var(--muted);
  line-height: 1.6;
  margin: 0 0 0.5714rem;
}
.search-result-heading button {
  border: 0;
  background: transparent;
  padding: 0;
  min-height: 1.2857rem;
}
.place-results > button {
  display: flex;
  justify-content: flex-start;
  width: 100%;
  text-align: left;
  padding: 0.7143rem 0.5rem;
  border: 0;
  background: transparent;
}
.place-results > button > svg {
  color: var(--accent);
}
.place-results b {
  font-size: 0.8571rem;
  font-weight: 500;
}
.place-results small {
  display: block;
  margin-top: 0.2857rem;
  color: var(--muted);
  font-size: 0.8571rem;
}
.draw-toolbar {
  position: absolute;
  top: 5.5714rem;
  left: 1.2857rem;
  z-index: 750;
  display: flex;
  align-items: center;
  gap: 0.1429rem;
  background: var(--surface);
  padding: 0.3571rem;
  border: 1px solid var(--line);
  border-radius: 0.5714rem;
  box-shadow: var(--shadow);
}
.draw-toolbar button {
  min-height: 2.3571rem;
  gap: 0.3571rem;
  padding: 0.5rem 0.6429rem;
  border: 0;
  font-size: 0.8571rem;
  background: transparent;
  color: #777970;
}
.draw-toolbar button.active {
  color: var(--accent);
  background: var(--accent-soft);
}
.tool-divider {
  height: 1.2143rem;
  width: 1px;
  background: var(--line);
  margin: 0 0.1429rem;
}
.map-guide {
  position: absolute;
  left: 1.2857rem;
  bottom: 3.0714rem;
  z-index: 750;
  display: flex;
  align-items: center;
  gap: 0.5714rem;
  padding: 0.7143rem 0.8571rem;
  background: #fffefdee;
  border: 1px solid var(--line);
  border-radius: 0.5rem;
  color: #666b5d;
  font-size: 0.8571rem;
}
.station-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: #78906b;
  border: 1px solid #4f6a53;
}
.guide-divider {
  width: 1px;
  height: 0.8571rem;
  background: var(--line);
  margin: 0 0.2143rem;
}
.map-controls {
  position: absolute;
  right: 1.2857rem;
  bottom: 3.0714rem;
  z-index: 750;
  display: flex;
  flex-direction: column;
  padding: 0.2857rem;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 0.5714rem;
  box-shadow: var(--shadow);
}
.map-controls button {
  border: 0;
  min-height: 2.4286rem;
  width: 2.4286rem;
  padding: 0.5rem;
  background: transparent;
  color: #61665b;
}
.map-controls > span {
  height: 1px;
  margin: 0.2143rem;
  background: var(--line);
}
.location-message {
  position: absolute;
  right: 4.8571rem;
  bottom: 10.3571rem;
  z-index: 800;
  max-width: min(20.3571rem, calc(100% - 6.4286rem));
  padding: 0.8571rem;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 0.5714rem;
  color: var(--muted);
  font-size: 0.8571rem;
  line-height: 1.7;
}
.map-state {
  position: absolute;
  left: 0;
  bottom: 0;
  z-index: 750;
  padding: 0.5rem 0.7143rem;
  font-size: 0.7857rem;
  color: #74776a;
  background: #fffefdcc;
  pointer-events: none;
  font-variant-numeric: tabular-nums;
}
.map-key-hint {
  position: absolute;
  left: 1.2857rem;
  top: 9.6429rem;
  z-index: 750;
  max-width: calc(100% - 2.5714rem);
  padding: 0.7143rem 0.9286rem;
  border: 1px solid #ddd0b1;
  border-radius: 0.5rem;
  background: #fcf8ed;
  color: #8d7443;
  font-size: 0.8571rem;
  line-height: 1.7;
}
:deep(.leaflet-container) {
  font-family: inherit;
}
:deep(.leaflet-control-attribution) {
  color: #777970;
  background: #fffefdcc;
  font-size: 0.7857rem;
}
:deep(.leaflet-control-attribution a) {
  color: #666b5d;
}
:deep(.leaflet-tooltip) {
  border: 1px solid var(--line);
  border-radius: 0.3571rem;
  color: var(--ink);
  background: var(--surface);
  box-shadow: var(--shadow);
  font-size: 0.8571rem;
}
:deep(.cluster-pin) {
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #4f6a53;
  color: white;
  border: 0.2857rem solid #cad5bf;
  font-weight: 600;
  font-size: 0.8571rem;
}
:deep(.marker-cluster-small),
:deep(.marker-cluster-medium),
:deep(.marker-cluster-large) {
  background: #cad5bfa0;
}
:deep(.marker-cluster-small div),
:deep(.marker-cluster-medium div),
:deep(.marker-cluster-large div) {
  background: #4f6a53;
  color: white;
}
@media (max-width: 1050px) {
  .draw-toolbar button {
    padding: 0.5rem;
  }
  .draw-toolbar button > span {
    display: none;
  }
  .map-guide {
    max-width: calc(100% - 5.8571rem);
    flex-wrap: wrap;
    gap: 0.4286rem;
  }
  .guide-divider {
    display: none;
  }
}
@media (max-width: 760px) {
  .map-search,
  .draw-toolbar {
    left: 0.8571rem;
  }
  .map-search {
    top: 0.8571rem;
    width: calc(100% - 1.7143rem);
  }
  .draw-toolbar {
    top: 5rem;
  }
  .draw-toolbar button {
    padding: 0.5rem 0.5714rem;
  }
  .map-guide {
    left: 0.8571rem;
    bottom: 2.8571rem;
  }
  .map-controls {
    right: 0.8571rem;
    bottom: 2.8571rem;
  }
  .map-key-hint {
    left: 0.8571rem;
    top: 8.7857rem;
    max-width: calc(100% - 1.7143rem);
  }
}
@media (max-width: 760px) and (min-width: 420px) {
  .draw-toolbar button > span {
    display: inline;
  }
}
</style>
