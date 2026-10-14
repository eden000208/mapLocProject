<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, nextTick, watch } from "vue";
import { api, errorText } from "./api";
import DetailUploadPane from "./DetailUploadPane.vue";
import L from "leaflet";
import {
  UserPlus,
  Search,
  UploadCloud,
  Download,
  CheckCircle2,
  X,
} from "lucide-vue-next";
const tab = ref("users"),
  users = ref<any[]>([]),
  stations = ref<any[]>([]),
  q = ref(""),
  stationPage = ref(1),
  stationTotal = ref(0),
  msg = ref(""),
  editing = ref<any>(null),
  kind = ref("user"),
  batch = ref<any>(null),
  preview = ref<any>(null),
  coord = ref("WGS84"),
  step = ref(1),
  busy = ref(false),
  mapEl = ref<HTMLElement>(),
  mapConfig = ref<any>(null);
let mini: L.Map | undefined;
let miniResize: ResizeObserver | undefined;
let miniResizeFrame = 0;
const modalEl = ref<HTMLFormElement>();
let modalOpener: HTMLElement | null = null;
watch(editing, async (value) => {
  if (value) {
    modalOpener = document.activeElement as HTMLElement;
    msg.value = "";
    await nextTick();
    modalEl.value
      ?.querySelector<HTMLElement>(
        "input:not(:disabled), select:not(:disabled)",
      )
      ?.focus();
  } else modalOpener?.focus();
});
function modalKeydown(event: KeyboardEvent) {
  if (event.key !== "Tab") return;
  const controls = modalEl.value?.querySelectorAll<HTMLElement>(
    "button:not(:disabled), input:not(:disabled), select:not(:disabled)",
  );
  if (!controls?.length) return;
  const first = controls[0],
    last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
const fields = [
  "lac",
  "cell_id",
  "station_name",
  "district",
  "service_center",
  "lng",
  "lat",
];
const labels: Record<string, string> = {
  lac: "lac",
  cell_id: "cell_id",
  station_name: "基站名称",
  district: "区县",
  service_center: "营服",
  lng: "经度",
  lat: "纬度",
};
const coordLabels: Record<string, string> = {
  WGS84: "全球坐标系",
  GCJ02: "国测坐标系",
  BD09: "百度坐标系",
};
async function load() {
  try {
    users.value = (await api.get("/admin/users")).data;
    const r = await api.get("/admin/stations", {
      params: { q: q.value, page: stationPage.value, size: 100 },
    });
    stations.value = r.data.items;
    stationTotal.value = r.data.total;
  } catch (e) {
    msg.value = errorText(e);
  }
}
function edit(u: any, type = "user") {
  kind.value = type;
  editing.value = u
    ? {
        ...u,
        districts: (u.districts || []).join(","),
        service_centers: (u.service_centers || []).join(","),
      }
    : {
        username: "",
        name: "",
        password: "",
        role: "analyst",
        is_active: true,
        view_plain: false,
        districts: "",
        service_centers: "",
      };
}
async function save() {
  try {
    const e = { ...editing.value };
    if (kind.value === "user") {
      e.districts = e.districts
        .split(/[,，]/)
        .map((x: string) => x.trim())
        .filter(Boolean);
      e.service_centers = e.service_centers
        .split(/[,，]/)
        .map((x: string) => x.trim())
        .filter(Boolean);
      if (!e.password) delete e.password;
      await (e.id
        ? api.patch(`/admin/users/${e.id}`, e)
        : api.post("/admin/users", e));
    } else {
      for (const [field, limit] of [
        ["lng", 180],
        ["lat", 90],
      ] as const) {
        if (
          String(e[field]).trim() === "" ||
          !Number.isFinite(Number(e[field])) ||
          Math.abs(Number(e[field])) > limit
        ) {
          msg.value = `${labels[field]}必须填写数字，范围为 -${limit}～${limit}（单位：度）。`;
          return;
        }
        e[field] = Number(e[field]);
      }
      await api.patch(`/admin/stations/${e.id}`, e);
    }
    editing.value = null;
    msg.value = "已保存";
    load();
  } catch (e) {
    msg.value = errorText(e);
  }
}
async function upload(ev: Event) {
  const f = (ev.target as HTMLInputElement).files?.[0];
  if (!f) return;
  busy.value = true;
  try {
    const data = new FormData();
    data.append("file", f);
    batch.value = (await api.post("/admin/stations/import", data)).data;
    step.value = 2;
    preview.value = null;
  } catch (e) {
    msg.value = errorText(e);
  } finally {
    busy.value = false;
  }
}
async function validate() {
  const missing = fields.filter((f) => !batch.value.mapping[f]);
  if (missing.length) {
    msg.value = "请选择对应文件列：" + missing.map((f) => labels[f]).join("、");
    return;
  }
  busy.value = true;
  msg.value = "";
  try {
    mapConfig.value = (await api.get("/config")).data;
    preview.value = (
      await api.post(`/admin/stations/import/${batch.value.batch_id}/preview`, {
        mapping: batch.value.mapping,
        coord_sys: coord.value,
      })
    ).data;
    step.value = 3;
  } catch (e) {
    msg.value = errorText(e);
  } finally {
    busy.value = false;
  }
}
// 预览容器重新挂载时重建地图，避免切换标签后留下空白画布。
watch(mapEl, () => {
  try {
    miniResize?.disconnect();
    cancelAnimationFrame(miniResizeFrame);
    mini?.remove();
    mini = undefined;
    if (mapEl.value && preview.value && mapConfig.value) {
      mini = L.map(mapEl.value, { maxZoom: 18 });
      const pts = preview.value.points || [];
      if (mapConfig.value.tianditu_key) {
        const url = `https://t{s}.tianditu.gov.cn/vec_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=vec&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk=${mapConfig.value.tianditu_key}`;
        L.tileLayer(url, {
          subdomains: "01234567",
          maxZoom: 18,
          attribution: "天地图",
        })
          .on(
            "tileerror",
            () =>
              (msg.value =
                "底图加载失败，请检查天地图 Key 的 Web 权限及网络；坐标预览仍可用"),
          )
          .addTo(mini);
        L.tileLayer(
          url.replace("/vec_w/", "/cva_w/").replace("LAYER=vec", "LAYER=cva"),
          { subdomains: "01234567", maxZoom: 18, attribution: "天地图注记" },
        ).addTo(mini);
      }
      const bounds: L.LatLngTuple[] = [];
      for (const p of pts) {
        for (const [key, color] of [
          ["WGS84", "#5b7c8b"],
          ["GCJ02", "#4f6a53"],
          ["BD09", "#ad8744"],
        ]) {
          const a = p[key];
          if (a) {
            L.circleMarker([a[1], a[0]], { color, radius: 5 })
              .bindTooltip(coordLabels[key] || key)
              .addTo(mini);
            bounds.push([a[1], a[0]]);
          }
        }
      }
      if (bounds.length) mini.fitBounds(bounds);
      else
        mini.setView(
          [mapConfig.value.map_center[1], mapConfig.value.map_center[0]],
          mapConfig.value.map_zoom,
        );
      miniResize = new ResizeObserver(() => {
        cancelAnimationFrame(miniResizeFrame);
        miniResizeFrame = requestAnimationFrame(() =>
          mini?.invalidateSize({ pan: false }),
        );
      });
      miniResize.observe(mapEl.value);
    }
  } catch (e) {
    msg.value = errorText(e);
  }
}, { flush: "post" });
async function confirmImport() {
  busy.value = true;
  try {
    const r = await api.post(
      `/admin/stations/import/${batch.value.batch_id}/confirm`,
    );
    msg.value = `已导入 ${r.data.imported} 行，跳过 ${r.data.error_count} 行`;
    step.value = 5;
    load();
  } catch (e) {
    msg.value = errorText(e);
  } finally {
    busy.value = false;
  }
}
async function download(path: string, name: string) {
  try {
    const r = await api.get(path, { responseType: "blob" });
    const url = URL.createObjectURL(r.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    msg.value = errorText(e);
  }
}
onMounted(load);
onBeforeUnmount(() => {
  miniResize?.disconnect();
  cancelAnimationFrame(miniResizeFrame);
  mini?.remove();
});
</script>
<template>
  <div class="content admin-content">
    <div class="tabs">
      <button
        v-for="(label, key) in {
          users: '账号管理',
          stations: '基站维护',
          import: '导入基站',
          details: '上传用户明细',
        }"
        :key="key"
        :class="{ active: tab === key }"
        @click="tab = key"
      >
        {{ label }}
      </button>
    </div>
    <p v-if="msg" class="inline-message" role="status">{{ msg }}</p>
    <DetailUploadPane v-if="tab === 'details'" />
    <div v-if="tab === 'users'">
      <div class="toolbar">
        <div class="section-title">
          <h2>账号管理</h2>
          <p class="muted">管理登录账号及可查询的区域范围。</p>
        </div>
        <button class="primary compact" @click="edit(null)">
          <UserPlus :size="16" />新建用户
        </button>
      </div>
      <div class="scroll-table">
        <table>
          <thead>
            <tr>
              <th>账号</th>
              <th>姓名</th>
              <th>角色</th>
              <th>区县 / 营服</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td>{{ u.username }}</td>
              <td>{{ u.name }}</td>
              <td>{{ u.role === "admin" ? "管理员" : "分析员" }}</td>
              <td>
                {{
                  [...(u.districts || []), ...(u.service_centers || [])].join(
                    "、",
                  ) || "未分配"
                }}
              </td>
              <td>
                <span
                  class="badge"
                  :data-status="u.is_active ? 'active' : 'inactive'"
                  >{{ u.is_active ? "启用" : "停用" }}</span
                >
              </td>
              <td><button @click="edit(u)">编辑</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div v-if="tab === 'stations'">
      <div class="section-title">
        <h2>基站维护</h2>
        <p class="muted">搜索、编辑并维护地图上的有效小区。</p>
      </div>
      <div class="toolbar">
        <input
          v-model="q"
          placeholder="输入基站名称"
          aria-label="搜索基站"
          @keyup.enter="
            stationPage = 1;
            load();
          "
        /><button
          @click="
            stationPage = 1;
            load();
          "
        >
          <Search :size="15" />搜索
        </button>
      </div>
      <div class="scroll-table">
        <table>
          <thead>
            <tr>
              <th>名称</th>
              <th>lac / cell_id</th>
              <th>区县</th>
              <th>营服</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in stations" :key="s.id">
              <td>{{ s.station_name }}</td>
              <td>{{ s.lac }} / {{ s.cell_id }}</td>
              <td>{{ s.district }}</td>
              <td>{{ s.service_center }}</td>
              <td>
                <span
                  class="badge"
                  :data-status="s.is_active ? 'active' : 'inactive'"
                  >{{ s.is_active ? "启用" : "停用" }}</span
                >
              </td>
              <td><button @click="edit(s, 'station')">编辑</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div v-if="tab === 'stations'" class="pagination">
      <span>共 {{ stationTotal }} 小区</span
      ><button
        :disabled="stationPage === 1"
        @click="
          stationPage--;
          load();
        "
      >
        上一页</button
      ><span>{{ stationPage }}</span
      ><button
        :disabled="stationPage * 100 >= stationTotal"
        @click="
          stationPage++;
          load();
        "
      >
        下一页
      </button>
    </div>
    <div v-if="tab === 'import'">
      <h2>导入基站</h2>
      <p class="hint">
        支持 .csv、.xlsx 表格，最多十万行。lac/cell_id 为非负整数；基站名称最多
        200 字，区县和营服最多 100 字；经度 -180～180，纬度
        -90～90。七个字段均需映射，可在表格内留空名称或区域。
      </p>
      <div class="steps">
        <span
          v-for="(s, i) in ['上传', '列映射', '校验预览', '确认', '完成']"
          :key="s"
          :class="{ active: step === i + 1 }"
          :aria-current="step === i + 1 ? 'step' : undefined"
        >
          <b>{{ i + 1 }}</b
          >{{ s }}</span
        >
      </div>
      <div v-if="step === 1" class="upload">
        <UploadCloud :size="32" />
        <h3>上传基站数据</h3>
        <p class="muted">选择 CSV 或 Excel 文件，按步骤完成映射与校验。</p>
        <button
          @click="download('/admin/stations/template', '基站导入模板.csv')"
        >
          <Download :size="15" />下载模板</button
        ><input
          type="file"
          accept=".csv,.xlsx"
          aria-label="上传基站 CSV 或 Excel 文件"
          :disabled="busy"
          @change="upload"
        />
      </div>
      <div v-if="step === 2">
        <div class="mapping">
          <label v-for="f in fields" :key="f"
            >{{ labels[f]
            }}<select v-model="batch.mapping[f]">
              <option value="">请选择对应列（必选）</option>
              <option v-for="h in batch.headers" :key="h">{{ h }}</option>
            </select></label
          >
        </div>
        <label
          >原始坐标系
          <select v-model="coord">
            <option value="WGS84">全球坐标系</option>
            <option value="GCJ02">国测坐标系</option>
            <option value="BD09">百度坐标系</option>
          </select></label
        ><button class="primary small" :disabled="busy" @click="validate">
          校验并预览
        </button>
      </div>
      <div v-if="step === 3 || step === 4">
        <div class="stats">
          <span
            >总行数 <b>{{ preview.total }}</b></span
          ><span
            >有效 <b>{{ preview.valid_count }}</b></span
          ><span
            >错误 <b>{{ preview.error_count }}</b></span
          ><span
            >新增 <b>{{ preview.new_count }}</b></span
          ><span
            >更新 <b>{{ preview.update_count }}</b></span
          >
        </div>
        <p v-if="!mapConfig?.tianditu_key" class="hint">
          底图暂不可用，请联系管理员；仍可查看坐标预览点。
        </p>
        <div ref="mapEl" class="mini-map"></div>
        <p class="hint">
          坐标：蓝色 全球坐标系 · 绿色 国测坐标系 · 黄色 百度坐标系
        </p>
        <div class="errors">
          <p v-for="(e, i) in preview.errors?.slice(0, 10)" :key="i">
            {{ typeof e === "string" ? e : `第 ${e.row} 行：${e.message}` }}
          </p>
        </div>
        <button
          @click="
            download(
              `/admin/stations/import/${batch.batch_id}/errors`,
              '导入错误.csv',
            )
          "
        >
          下载错误报告</button
        ><button @click="step = 2">返回映射</button
        ><button
          v-if="step === 3"
          class="primary small"
          :disabled="!preview.valid_count"
          @click="step = 4"
        >
          继续确认</button
        ><button
          v-else
          class="primary small"
          :disabled="busy"
          @click="confirmImport"
        >
          确认导入 {{ preview.valid_count }} 行
        </button>
      </div>
      <div v-if="step === 5" class="import-done">
        <CheckCircle2 :size="36" />
        <h3>基站数据已导入</h3>
        <p>{{ msg }}</p>
        <button
          @click="
            step = 1;
            batch = null;
          "
        >
          继续导入
        </button>
      </div>
    </div>
    <div
      v-if="editing"
      class="modal-backdrop"
      @click.self="editing = null"
      @keydown.esc="editing = null"
    >
      <form
        ref="modalEl"
        class="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-title"
        @keydown="modalKeydown"
        @submit.prevent="save"
      >
        <div class="modal-heading">
          <h2 id="edit-title">
            {{
              kind === "user"
                ? editing.id
                  ? "编辑账号"
                  : "新建用户"
                : "编辑基站"
            }}
          </h2>
          <button
            type="button"
            class="text-button"
            aria-label="关闭编辑"
            @click="editing = null"
          >
            <X :size="18" />
          </button>
        </div>
        <template v-if="kind === 'user'"
          ><label
            >账号<input
              v-model="editing.username"
              :disabled="!!editing.id"
              required /></label
          ><label>姓名<input v-model="editing.name" /></label
          ><label
            >密码<input
              v-model="editing.password"
              type="password"
              :required="!editing.id"
              placeholder="留空保留现密码" /></label
          ><label
            >角色<select v-model="editing.role">
              <option value="analyst">分析员</option>
              <option value="admin">管理员</option>
            </select></label
          ><label>区县（逗号分隔）<input v-model="editing.districts" /></label
          ><label
            >营服（逗号分隔）<input v-model="editing.service_centers" /></label
          ><label
            ><input
              type="checkbox"
              v-model="editing.view_plain"
            />允许明文查看</label
          ></template
        ><template v-else
          ><label
            v-for="f in [
              'station_name',
              'district',
              'service_center',
              'lng',
              'lat',
            ]"
            :key="f"
            >{{ labels[f]
            }}<input
              v-model="editing[f]"
              :type="['lng', 'lat'].includes(f) ? 'number' : 'text'"
              :step="['lng', 'lat'].includes(f) ? 'any' : undefined"
              :min="f === 'lng' ? -180 : f === 'lat' ? -90 : undefined"
              :max="f === 'lng' ? 180 : f === 'lat' ? 90 : undefined"
              :maxlength="f === 'station_name' ? 200 : 100"
              :placeholder="
                f === 'lng'
                  ? '-180～180 度'
                  : f === 'lat'
                    ? '-90～90 度'
                    : '请输入' + labels[f]
              " /></label></template
        ><label
          ><input type="checkbox" v-model="editing.is_active" />启用</label
        >
        <p v-if="msg" class="inline-message" role="status">{{ msg }}</p>
        <div class="toolbar">
          <button type="button" @click="editing = null">取消</button
          ><button type="submit" class="primary compact">保存更改</button>
        </div>
      </form>
    </div>
  </div>
</template>
