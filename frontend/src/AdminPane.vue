<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, nextTick } from "vue";
import { api, errorText } from "./api";
import L from "leaflet";
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
const fields = [
  "lac",
  "cell_id",
  "station_name",
  "district",
  "service_center",
  "lng",
  "lat",
];
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
    } else await api.patch(`/admin/stations/${e.id}`, e);
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
  busy.value = true;
  try {
    mapConfig.value = (await api.get("/config")).data;
    preview.value = (
      await api.post(`/admin/stations/import/${batch.value.batch_id}/preview`, {
        mapping: batch.value.mapping,
        coord_sys: coord.value,
      })
    ).data;
    step.value = 3;
    await nextTick();
    mini?.remove();
    if (mapEl.value) {
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
          ["WGS84", "#1677ff"],
          ["GCJ02", "#14a88b"],
          ["BD09", "#d09522"],
        ]) {
          const a = p[key];
          if (a) {
            L.circleMarker([a[1], a[0]], { color, radius: 5 })
              .bindTooltip(key)
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
    }
  } catch (e) {
    msg.value = errorText(e);
  } finally {
    busy.value = false;
  }
}
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
onBeforeUnmount(() => mini?.remove());
</script>
<template>
  <div class="content">
    <div class="tabs">
      <button
        v-for="(label, key) in {
          users: '账号管理',
          stations: '基站维护',
          import: '导入基站',
        }"
        :key="key"
        :class="{ active: tab === key }"
        @click="tab = key"
      >
        {{ label }}
      </button>
    </div>
    <p class="hint">{{ msg }}</p>
    <div v-if="tab === 'users'">
      <div class="toolbar">
        <h1>账号管理</h1>
        <button @click="edit(null)">＋ 新建用户</button>
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
              <th></th>
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
              <td>{{ u.is_active ? "启用" : "停用" }}</td>
              <td><button @click="edit(u)">编辑</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div v-if="tab === 'stations'">
      <h1>基站维护</h1>
      <div class="toolbar">
        <input
          v-model="q"
          placeholder="搜索基站"
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
          搜索
        </button>
      </div>
      <div class="scroll-table">
        <table>
          <thead>
            <tr>
              <th>名称</th>
              <th>LAC / Cell ID</th>
              <th>区县</th>
              <th>营服</th>
              <th>状态</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in stations" :key="s.id">
              <td>{{ s.station_name }}</td>
              <td>{{ s.lac }} / {{ s.cell_id }}</td>
              <td>{{ s.district }}</td>
              <td>{{ s.service_center }}</td>
              <td>{{ s.is_active ? "启用" : "停用" }}</td>
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
      <h1>导入基站</h1>
      <div class="steps">
        <span
          v-for="(s, i) in ['上传', '列映射', '校验预览', '确认', '完成']"
          :key="s"
          :class="{ active: step === i + 1 }"
          >{{ i + 1 }} {{ s }}</span
        >
      </div>
      <div v-if="step === 1" class="upload">
        <button
          @click="download('/admin/stations/template', '基站导入模板.csv')"
        >
          下载模板</button
        ><input
          type="file"
          accept=".csv,.xlsx"
          :disabled="busy"
          @change="upload"
        />
      </div>
      <div v-if="step === 2">
        <div class="mapping">
          <label v-for="f in fields" :key="f"
            >{{ f
            }}<select v-model="batch.mapping[f]">
              <option value="">不映射</option>
              <option v-for="h in batch.headers" :key="h">{{ h }}</option>
            </select></label
          >
        </div>
        <label
          >原始坐标系
          <select v-model="coord">
            <option>WGS84</option>
            <option>GCJ02</option>
            <option>BD09</option>
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
          未配置天地图 Key，底图暂不可用；仍可查看坐标预览点。请在 .env 设置
          TIANDITU_KEY。
        </p>
        <div ref="mapEl" class="mini-map"></div>
        <p class="hint">坐标：蓝色 WGS84 · 绿色 GCJ02 · 黄色 BD09</p>
        <div class="errors">
          <p v-for="(e, i) in preview.errors?.slice(0, 10)" :key="i">
            {{ typeof e === "string" ? e : JSON.stringify(e) }}
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
      <div v-if="step === 5">
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
    <div v-if="editing" class="modal-backdrop">
      <form class="modal" @submit.prevent="save">
        <h2>{{ kind === "user" ? "编辑账号" : "编辑基站" }}</h2>
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
            >{{ f }}<input v-model="editing[f]" /></label></template
        ><label
          ><input type="checkbox" v-model="editing.is_active" />启用</label
        >
        <div class="toolbar">
          <button type="button" @click="editing = null">取消</button
          ><button type="submit">保存</button>
        </div>
      </form>
    </div>
  </div>
</template>
