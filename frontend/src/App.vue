<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { api, errorText, setCsrf, runOperation } from "./api";
import type { User, Cell, Task } from "./types";
import MapPane from "./MapPane.vue";
import AdminPane from "./AdminPane.vue";
import {
  Map as MapIcon,
  History,
  Settings2,
  KeyRound,
  LogOut,
  MapPin,
  ArrowRight,
  ArrowLeft,
  RefreshCw,
  Download,
  X,
  Layers,
  Check,
  ShieldCheck,
  Radio,
  Search,
  ChevronRight,
} from "lucide-vue-next";
const user = ref<User | null>(null),
  loading = ref(true),
  page = ref("query"),
  notice = ref(""),
  busy = ref(false);
const loginForm = ref({ username: "", password: "" }),
  pwd = ref({ old_password: "", new_password: "" });
const config = ref<any>(null);
const cells = ref<Cell[]>([]),
  months = ref<string[]>([]),
  selectedMonths = ref<string[]>([]),
  nets = ref<string[]>(["local"]),
  purpose = ref("");
const tasks = ref<Task[]>([]),
  current = ref<Task | null>(null),
  rows = ref<any[]>([]),
  rowNet = ref("local"),
  plain = ref(false),
  rowPage = ref(1),
  total = ref(0);
const size = ref(50);
const pageTitle = computed(
  () =>
    ({
      query: "地图查询",
      tasks: "我的查询",
      result: "查询结果",
      admin: "管理工作台",
      password: "账号安全",
    })[page.value] || "工作台",
);
const pageDescription = computed(
  () =>
    ({
      query: "从地图出发，找到需要的区域数据。",
      tasks: "查看查询进度，或复用已有的查询条件。",
      result: "查看查询明细与统计，按需导出结果。",
      admin: "维护账号、基站与区域数据。",
      password: "管理您的登录密码。",
    })[page.value],
);
const selectionStations = computed(
  () =>
    new Set(
      cells.value.map(
        (c) =>
          `${c.station_name || ""}|${c.lng ?? c.lac}|${c.lat ?? c.cell_id}`,
      ),
    ).size,
);
const navigation = [
  { key: "query", label: "地图查询", icon: MapIcon },
  { key: "tasks", label: "我的查询", icon: History },
  { key: "admin", label: "管理工作台", icon: Settings2 },
];
const isAdmin = computed(() => user.value?.role === "admin");
const isRunning = computed(() =>
  ["PENDING", "RUNNING"].includes(current.value?.status || ""),
);
const statusName = (s: string) =>
  ({
    PENDING: "排队中",
    RUNNING: "查询中",
    SUCCESS: "已完成",
    FAILED: "失败",
    CANCELLED: "已取消",
    EXPIRED: "已过期",
  })[s] || s;
let timer: ReturnType<typeof setInterval> | undefined;
let rowSeq = 0;
let monthSeq = 0;
async function me() {
  try {
    user.value = (await api.get("/auth/me")).data;
    setCsrf(user.value?.csrf_token || "");
    if (user.value?.must_change_pwd) page.value = "password";
  } catch {
    user.value = null;
  } finally {
    loading.value = false;
  }
}
async function boot() {
  if (user.value?.must_change_pwd) return;
  try {
    config.value = (await api.get("/config")).data;
    await loadMonths();
  } catch (e) {
    notice.value = errorText(e);
  }
}
async function login() {
  busy.value = true;
  try {
    user.value = (await api.post("/auth/login", loginForm.value)).data;
    setCsrf(user.value?.csrf_token || "");
    loginForm.value.password = "";
    page.value = user.value?.must_change_pwd ? "password" : "query";
    notice.value = "";
    await boot();
  } catch (e) {
    notice.value = errorText(e);
  } finally {
    busy.value = false;
  }
}
async function logout() {
  try {
    await api.post("/auth/logout");
  } finally {
    user.value = null;
    setCsrf("");
    current.value = null;
    rows.value = [];
    cells.value = [];
    notice.value = "";
  }
}
async function changePwd() {
  busy.value = true;
  try {
    await api.post("/auth/change-password", pwd.value);
    pwd.value = { old_password: "", new_password: "" };
    await me();
    page.value = "query";
    await boot();
    notice.value = "密码已更新";
  } catch (e) {
    notice.value = errorText(e);
  } finally {
    busy.value = false;
  }
}
// 管理员与分析员共用查询流程，实际数据范围仍由后端校验。
async function loadMonths() {
  if (!user.value || user.value.must_change_pwd) return;
  const seq = ++monthSeq;
  try {
    const r = await api.get("/meta/months", {
      params: { nets: nets.value.join(",") },
    });
    if (seq !== monthSeq) return;
    months.value = r.data.months;
    selectedMonths.value = selectedMonths.value.filter((m) =>
      months.value.includes(m),
    );
  } catch (e) {
    notice.value = errorText(e);
  }
}
function select(add: Cell[]) {
  const merged = new Map(cells.value.map((c) => [`${c.lac}/${c.cell_id}`, c]));
  for (const c of add) merged.set(`${c.lac}/${c.cell_id}`, c);
  cells.value = [...merged.values()];
  notice.value = `已选择 ${cells.value.length} 个小区`;
}
async function submit() {
  if (
    !selectedMonths.value.length ||
    !cells.value.length ||
    !purpose.value.trim() ||
    !nets.value.length
  ) {
    notice.value = "请选择小区、网别、月份并填写事由";
    return;
  }
  busy.value = true;
  try {
    current.value = (
      await api.post("/queries", {
        cells: cells.value,
        months: selectedMonths.value,
        nets: nets.value,
        purpose: purpose.value,
      })
    ).data;
    rowPage.value = 1;
    rowNet.value = nets.value[0] || "local";
    plain.value = false;
    rows.value = [];
    page.value = "result";
    notice.value = "查询已提交";
  } catch (e) {
    notice.value = errorText(e);
  } finally {
    busy.value = false;
  }
}
async function loadTasks() {
  try {
    tasks.value =
      (await api.get("/queries", { params: { page: 1, size: 100 } })).data
        .items || [];
  } catch (e) {
    notice.value = errorText(e);
  }
}
async function openTask(t: Task) {
  plain.value = false;
  rows.value = [];
  rowPage.value = 1;
  rowNet.value = t.nets[0] || "local";
  current.value = t;
  page.value = "result";
  await refreshTask();
  await loadRows();
}
async function refreshTask() {
  if (!current.value) return;
  const id = current.value.id;
  try {
    const task = (await api.get(`/queries/${id}`)).data;
    if (current.value?.id === id) {
      const old = current.value.status;
      current.value = task;
      if (old !== task.status && !["PENDING", "RUNNING"].includes(task.status))
        await loadRows();
    }
  } catch (e) {
    notice.value = errorText(e);
  }
}
async function loadRows() {
  const id = current.value?.id;
  const seq = ++rowSeq;
  rows.value = [];
  total.value = 0;
  if (!id || isRunning.value || current.value?.status !== "SUCCESS") return;
  try {
    const r = await api.get(`/queries/${id}/rows`, {
      params: {
        net: rowNet.value,
        page: rowPage.value,
        size: size.value,
        plain: plain.value,
      },
    });
    if (seq === rowSeq && current.value?.id === id) {
      rows.value = r.data.items || [];
      total.value = r.data.total;
    }
  } catch (e) {
    notice.value = errorText(e);
  }
}
async function cancel(t = current.value) {
  if (!t) return;
  try {
    await api.post(`/queries/${t.id}/cancel`);
    notice.value = "已请求取消";
    await refreshTask();
    await loadTasks();
  } catch (e) {
    notice.value = errorText(e);
  }
}
async function reuse(t: Task) {
  try {
    const r = await api.post("/selections/resolve", {
      type: "cells",
      cells: t.cell_keys,
    });
    cells.value = r.data.cells;
    selectedMonths.value = [...t.months];
    nets.value = [...t.nets];
    purpose.value = t.purpose;
    page.value = "query";
    await loadMonths();
    notice.value = "已复用条件，请核对后提交";
  } catch (e) {
    notice.value = errorText(e);
  }
}
async function exportXlsx() {
  if (!current.value) return;
  busy.value = true;
  try {
    const blob = await runOperation("export", current.value.id, plain.value);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bsq-${current.value.id}.xlsx`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e: any) {
    if (e.response?.data instanceof Blob) {
      try {
        notice.value = JSON.parse(await e.response.data.text()).message;
      } catch {
        notice.value = "导出失败";
      }
    } else notice.value = errorText(e);
  } finally {
    busy.value = false;
  }
}
watch(page, (p) => {
  notice.value = "";
  if (p === "tasks") loadTasks();
  if (p === "query") loadMonths();
});
watch(nets, loadMonths, { deep: true });
watch([rowNet, plain, size], () => {
  rowPage.value = 1;
  loadRows();
});
watch(rowPage, loadRows);
onMounted(async () => {
  await me();
  if (user.value) await boot();
  timer = setInterval(() => {
    if (page.value === "result" && isRunning.value) refreshTask();
    if (page.value === "tasks") loadTasks();
  }, 2500);
});
function sessionExpired() {
  user.value = null;
  setCsrf("");
  rows.value = [];
  current.value = null;
  notice.value = "会话已失效，请重新登录";
}
window.addEventListener("bsq-session-expired", sessionExpired);
onBeforeUnmount(() => {
  clearInterval(timer);
  window.removeEventListener("bsq-session-expired", sessionExpired);
});
</script>
<template>
  <div v-if="loading" class="center">
    <div class="loading-mark">
      <Radio :size="28" /><span>正在打开工作台…</span>
    </div>
  </div>
  <div v-else-if="!user" class="login">
    <div class="login-brand">
      <span class="brand-symbol"><Radio :size="22" /></span><b>BSQ</b
      ><span>基站圈选查询</span>
    </div>
    <div class="login-layout">
      <section class="login-intro">
        <div class="territory-art" aria-hidden="true">
          <svg viewBox="0 0 380 250" fill="none">
            <path
              d="M0 192C87 182 65 88 169 106S260 226 380 146M0 154C85 165 86 38 180 71S274 193 380 109M0 115C86 126 110 0 204 38S290 163 380 72M0 226C98 223 81 126 165 141S260 258 380 184"
              stroke="currentColor"
            />
            <path
              d="M84 71L249 54L312 151L171 208L84 71Z"
              stroke="var(--accent)"
              stroke-dasharray="5 6"
            />
            <circle cx="84" cy="71" r="6" fill="var(--accent)" />
            <circle cx="249" cy="54" r="6" fill="var(--accent)" />
            <circle cx="312" cy="151" r="6" fill="var(--accent)" />
            <circle cx="171" cy="208" r="6" fill="var(--accent)" />
            <circle cx="193" cy="125" r="20" fill="var(--accent-soft)" />
            <circle cx="193" cy="125" r="7" fill="var(--accent)" />
          </svg>
        </div>
        <h1>每一次查询，<br />从一片区域开始。</h1>
        <p>
          圈选地图上的基站，按月份查询本网与异网数据。让区域选择、数据查询与结果导出，在同一个工作台完成。
        </p>
        <div class="login-flow">
          <span><MapPin :size="16" />圈选区域</span
          ><ChevronRight :size="14" /><span><Search :size="16" />查询数据</span
          ><ChevronRight :size="14" /><span
            ><Download :size="16" />导出结果</span
          >
        </div>
      </section>
      <form class="login-card" @submit.prevent="login">
        <h2>欢迎回来</h2>
        <p class="muted">登录 BSQ，继续您的区域查询。</p>
        <label for="login-username">用户名</label
        ><input
          id="login-username"
          v-model="loginForm.username"
          placeholder="请输入用户名"
          autocomplete="username"
          required
        />
        <label for="login-password">密码</label
        ><input
          id="login-password"
          v-model="loginForm.password"
          type="password"
          placeholder="请输入密码"
          autocomplete="current-password"
          required
        />
        <button class="primary" :disabled="busy">
          {{ busy ? "登录中…" : "登录工作台" }}<ArrowRight :size="16" />
        </button>
        <p v-if="notice" class="inline-message error" role="alert">
          {{ notice }}
        </p>
        <div class="login-note">
          <ShieldCheck :size="15" />使用已分配的账号登录
        </div>
      </form>
    </div>
    <footer class="login-footer">BSQ 基站圈选查询系统</footer>
  </div>
  <div v-else class="app">
    <aside class="app-sidebar">
      <div class="brand">
        <span class="brand-symbol"><Radio :size="21" /></span>
        <div><b>BSQ</b><small>基站圈选查询</small></div>
      </div>
      <div class="sidebar-section-label">工作空间</div>
      <nav v-if="!user.must_change_pwd" aria-label="主导航">
        <template v-for="item in navigation" :key="item.key">
          <button
            v-if="item.key !== 'admin' || isAdmin"
            :class="{
              active:
                page === item.key ||
                (item.key === 'tasks' && page === 'result'),
            }"
            :aria-current="page === item.key ? 'page' : undefined"
            @click="page = item.key"
          >
            <component :is="item.icon" :size="18" /><span>{{
              item.label
            }}</span>
          </button>
        </template>
      </nav>
      <div class="sidebar-bottom">
        <div class="scope-note">
          <ShieldCheck :size="16" /><span>{{
            isAdmin ? "全部有效小区可查询" : "按已授权区域查询"
          }}</span>
        </div>
        <div class="user-profile">
          <span class="avatar">{{
            (user.name || user.username).slice(0, 1)
          }}</span>
          <div>
            <b>{{ user.name || user.username }}</b
            ><small>{{ isAdmin ? "管理员" : "分析员" }}</small>
          </div>
        </div>
        <div class="user-actions">
          <button
            :class="{ active: page === 'password' }"
            @click="page = 'password'"
          >
            <KeyRound :size="15" />修改密码</button
          ><button @click="logout"><LogOut :size="15" />退出</button>
        </div>
      </div>
    </aside>
    <div class="app-body">
      <header class="page-header">
        <div>
          <h1>{{ pageTitle }}</h1>
          <p>{{ pageDescription }}</p>
        </div>
        <span class="workspace-tag"><span></span>BSQ 工作台</span>
      </header>
      <div v-if="notice" class="toast" role="status">
        <Check :size="16" /><span>{{ notice }}</span
        ><button aria-label="关闭提示" @click="notice = ''">
          <X :size="16" />
        </button>
      </div>
      <main>
        <section
          v-if="page === 'query' && !user.must_change_pwd"
          class="workspace"
        >
          <aside class="panel">
            <div class="panel-title">
              <div>
                <h2>设置查询条件</h2>
                <p class="muted">选择区域，再指定查询范围。</p>
              </div>
              <Settings2 :size="18" />
            </div>
            <div class="form-section">
              <div class="field-heading">
                <label>查询网别</label><span>可多选</span>
              </div>
              <div class="seg">
                <label
                  v-for="n in ['local', 'other']"
                  :key="n"
                  :class="{ selected: nets.includes(n) }"
                  ><input type="checkbox" :value="n" v-model="nets" /><span>{{
                    n === "local" ? "本网" : "异网"
                  }}</span
                  ><Check v-if="nets.includes(n)" :size="14"
                /></label>
              </div>
            </div>
            <div class="form-section">
              <div class="field-heading">
                <label>查询月份</label
                ><span>最多 {{ config?.max_months || 3 }} 个月</span>
              </div>
              <div class="month-list">
                <label
                  v-for="m in months"
                  :key="m"
                  :class="{ selected: selectedMonths.includes(m) }"
                  ><input
                    type="checkbox"
                    :value="m"
                    v-model="selectedMonths"
                  />{{ m }}</label
                >
                <p v-if="!months.length" class="muted">
                  暂无可用月份，请检查网别或数据来源。
                </p>
              </div>
              <p
                v-if="selectedMonths.length > (config?.max_months || 3)"
                class="error field-help"
                role="alert"
              >
                已超过月份上限，请减少选择。
              </p>
            </div>
            <div class="form-section">
              <div class="field-heading">
                <label for="query-purpose">查询事由</label
                ><span>{{ purpose.length }} / 500</span>
              </div>
              <textarea
                id="query-purpose"
                v-model="purpose"
                maxlength="500"
                placeholder="填写本次查询的业务用途…"
              ></textarea>
            </div>
            <div class="selection-section">
              <div class="selection-head">
                <h3>
                  <Layers :size="16" />已选小区<span class="count-pill">{{
                    cells.length
                  }}</span>
                </h3>
                <button
                  class="text-button"
                  :disabled="!cells.length"
                  @click="cells = []"
                >
                  清空
                </button>
              </div>
              <p v-if="cells.length" class="field-help">
                来自 {{ selectionStations }} 个站点 · 上限
                {{ config?.max_cells || 2000 }} 个小区
              </p>
              <div class="chips">
                <span v-for="c in cells" :key="`${c.lac}-${c.cell_id}`"
                  >{{ c.station_name || `${c.lac}/${c.cell_id}`
                  }}<button
                    :aria-label="`移除 ${c.station_name || '小区'}`"
                    @click="cells = cells.filter((x) => x !== c)"
                  >
                    <X :size="12" /></button
                ></span>
                <div v-if="!cells.length" class="selection-empty">
                  <MapPin :size="25" /><b>在地图上选择区域</b>
                  <p>点击站点，或用圈选工具<br />添加需要查询的小区。</p>
                </div>
              </div>
              <p
                v-if="cells.length > (config?.max_cells || 2000)"
                class="error field-help"
                role="alert"
              >
                已超过小区上限，请减少选择。
              </p>
            </div>
            <div class="panel-submit">
              <button
                class="primary"
                :disabled="
                  busy ||
                  cells.length > (config?.max_cells || 2000) ||
                  selectedMonths.length > (config?.max_months || 3)
                "
                @click="submit"
              >
                {{ busy ? "提交中…" : "开始查询" }}<ArrowRight :size="16" />
              </button>
              <p>查询结果默认脱敏展示</p>
            </div>
          </aside>
          <MapPane
            v-if="config"
            :config="config"
            @selected="select"
            @error="notice = $event"
          />
          <div v-else class="map-unavailable">
            <MapIcon :size="36" />
            <h2>地图暂未就绪</h2>
            <p class="muted">重新加载地图配置后继续查询。</p>
            <button @click="boot"><RefreshCw :size="15" />重新加载</button>
          </div>
        </section>
        <section v-else-if="page === 'tasks'" class="content">
          <div class="toolbar">
            <div class="section-title">
              <h2>查询记录</h2>
              <p class="muted">共 {{ tasks.length }} 条已加载记录</p>
            </div>
            <button @click="loadTasks"><RefreshCw :size="15" />刷新</button
            ><button class="primary compact" @click="page = 'query'">
              <MapIcon :size="16" />新建查询
            </button>
          </div>
          <div class="scroll-table">
            <table>
              <thead>
                <tr>
                  <th>创建时间</th>
                  <th>状态</th>
                  <th>小区数</th>
                  <th>月份</th>
                  <th>查询事由</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="t in tasks" :key="t.id">
                  <td>{{ new Date(t.created_at).toLocaleString() }}</td>
                  <td>
                    <span class="badge" :data-status="t.status">{{
                      statusName(t.status)
                    }}</span>
                  </td>
                  <td>{{ t.cell_keys.length }}</td>
                  <td>{{ t.months.join("、") }}</td>
                  <td>{{ t.purpose }}</td>
                  <td class="actions">
                    <button @click="openTask(t)">查看</button
                    ><button @click="reuse(t)">复用条件</button
                    ><button
                      v-if="['PENDING', 'RUNNING'].includes(t.status)"
                      @click="cancel(t)"
                    >
                      取消
                    </button>
                  </td>
                </tr>
                <tr v-if="!tasks.length">
                  <td colspan="6" class="empty">
                    <History :size="28" />
                    <h3>还没有查询记录</h3>
                    <p>选择地图上的区域，开始您的第一次查询。</p>
                    <button @click="page = 'query'">前往地图查询</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <section v-else-if="page === 'result'" class="content">
          <div class="toolbar">
            <button class="text-button" @click="page = 'tasks'">
              <ArrowLeft :size="16" />返回查询记录
            </button>
            <div class="toolbar-spacer"></div>
            <label class="checkbox-label"
              ><input
                type="checkbox"
                v-model="plain"
                :disabled="(!isAdmin && !user.view_plain) || isRunning"
              />显示明文</label
            ><button v-if="isRunning" @click="cancel()">取消任务</button
            ><button
              class="primary compact"
              :disabled="busy || isRunning || current?.status !== 'SUCCESS'"
              @click="exportXlsx"
            >
              <Download :size="16" />{{ busy ? "正在导出…" : "导出 XLSX" }}
            </button>
          </div>
          <div class="status-card">
            <div class="status-heading">
              <h2>{{ current?.purpose || "查询任务" }}</h2>
              <span class="badge" :data-status="current?.status">{{
                statusName(current?.status || "")
              }}</span>
            </div>
            <p v-if="isRunning">
              批次 {{ current?.completed_batches }} /
              {{ current?.total_batches }} · 已读取
              {{ (current?.rows_local || 0) + (current?.rows_other || 0) }} 行
            </p>
            <progress
              v-if="isRunning"
              :value="current?.completed_batches || 0"
              :max="current?.total_batches || 1"
              aria-label="查询进度"
            ></progress>
            <p v-if="current?.error" class="error">{{ current.error }}</p>
            <p class="muted">
              结果有效期至
              {{
                current?.expire_at
                  ? new Date(current.expire_at).toLocaleString()
                  : "—"
              }}
            </p>
          </div>
          <div class="stats result-stats">
            <div>
              <span>本网查询结果</span
              ><strong
                >{{ (current?.rows_local || 0).toLocaleString()
                }}<small>行</small></strong
              >
              <p>
                {{ (current?.uniq_local || 0).toLocaleString() }} 个去重号码
              </p>
            </div>
            <div>
              <span>异网查询结果</span
              ><strong
                >{{ (current?.rows_other || 0).toLocaleString()
                }}<small>行</small></strong
              >
              <p>
                {{ (current?.uniq_other || 0).toLocaleString() }} 个去重号码
              </p>
            </div>
            <div class="result-display-note">
              <ShieldCheck :size="23" /><b>{{
                plain ? "正在显示明文" : "已保护号码信息"
              }}</b>
              <p>
                {{
                  plain
                    ? "导出文件将包含明文数据"
                    : "号码默认脱敏，明文操作需要权限"
                }}
              </p>
            </div>
          </div>
          <div class="table-heading">
            <div class="tabs">
              <button
                :class="{ active: rowNet === 'local' }"
                @click="rowNet = 'local'"
              >
                本网明细</button
              ><button
                :class="{ active: rowNet === 'other' }"
                @click="rowNet = 'other'"
              >
                异网明细
              </button>
            </div>
            <span class="muted">{{ plain ? "明文显示" : "脱敏显示" }}</span>
          </div>
          <div class="scroll-table">
            <table>
              <thead>
                <tr>
                  <th>号码</th>
                  <th>月份</th>
                  <th>LAC</th>
                  <th>Cell ID</th>
                  <th>小区名称</th>
                  <th>街道</th>
                  <th v-if="plain && rowNet === 'local'">UID</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(r, i) in rows" :key="i">
                  <td>{{ r.device_number || "—" }}</td>
                  <td>{{ r.month_id }}</td>
                  <td>{{ r.lac }}</td>
                  <td>{{ r.cell_id }}</td>
                  <td>{{ r.cell_name || "—" }}</td>
                  <td>{{ r.street_name || "—" }}</td>
                  <td v-if="plain && rowNet === 'local'">{{ r.uid || "—" }}</td>
                </tr>
                <tr v-if="!rows.length">
                  <td
                    :colspan="plain && rowNet === 'local' ? 7 : 6"
                    class="empty"
                  >
                    <Search :size="28" />
                    <h3>
                      {{ isRunning ? "正在查询，请稍候…" : "暂无可展示结果" }}
                    </h3>
                    <p>
                      {{
                        isRunning
                          ? "完成后将自动展示查询结果。"
                          : "请核对任务状态，或切换网别查看明细。"
                      }}
                    </p>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="pagination">
            <span>共 {{ total }} 行</span
            ><select v-model="size" aria-label="每页行数">
              <option :value="50">50 / 页</option>
              <option :value="100">100 / 页</option></select
            ><button :disabled="rowPage === 1" @click="rowPage--">上一页</button
            ><span
              >{{ rowPage }} / {{ Math.max(1, Math.ceil(total / size)) }}</span
            ><button :disabled="rowPage * size >= total" @click="rowPage++">
              下一页
            </button>
          </div>
        </section>
        <section v-else-if="page === 'password'" class="content narrow">
          <div class="password-icon"><KeyRound :size="24" /></div>
          <h2>
            {{
              user.must_change_pwd ? "首次登录，请设置新密码" : "修改登录密码"
            }}
          </h2>
          <p class="muted">
            {{
              user.must_change_pwd
                ? "完成密码修改后，即可进入工作台。"
                : "使用至少 8 位的新密码保护您的账号。"
            }}
          </p>
          <form @submit.prevent="changePwd">
            <label for="old-password">当前密码</label
            ><input
              id="old-password"
              v-model="pwd.old_password"
              type="password"
              placeholder="请输入当前密码"
              autocomplete="current-password"
              required
            /><label for="new-password">新密码</label
            ><input
              id="new-password"
              v-model="pwd.new_password"
              type="password"
              placeholder="至少 8 位"
              minlength="8"
              autocomplete="new-password"
              required
            /><button class="primary" :disabled="busy">
              {{ busy ? "保存中…" : "保存新密码" }}<Check :size="16" />
            </button>
          </form>
        </section>
        <AdminPane v-else-if="isAdmin && page === 'admin'" />
      </main>
    </div>
  </div>
</template>
