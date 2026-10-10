<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { api, errorText, setCsrf } from "./api";
import type { User, Cell, Task } from "./types";
import MapPane from "./MapPane.vue";
import AdminPane from "./AdminPane.vue";
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
    const r = await api.post(`/queries/${current.value.id}/export`, null, {
      params: { plain: plain.value },
      responseType: "blob",
    });
    const url = URL.createObjectURL(r.data);
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
  <div v-if="loading" class="center">加载中…</div>
  <div v-else-if="!user" class="login">
    <form class="login-card" @submit.prevent="login">
      <div class="brand">BSQ <span>基站圈选查询</span></div>
      <p class="muted">登录后开始您的区域查询</p>
      <input
        v-model="loginForm.username"
        placeholder="用户名"
        autocomplete="username"
        required
      /><input
        v-model="loginForm.password"
        type="password"
        placeholder="密码"
        autocomplete="current-password"
        required
      /><button :disabled="busy">{{ busy ? "登录中…" : "登录" }}</button>
      <p class="hint">{{ notice }}</p>
    </form>
  </div>
  <div v-else class="app">
    <header>
      <div class="brand">BSQ <span>基站圈选查询</span></div>
      <nav v-if="!user.must_change_pwd">
        <template v-if="user"
          ><button
            :class="{ active: page === 'query' }"
            @click="page = 'query'"
          >
            地图查询</button
          ><button
            :class="{ active: page === 'tasks' }"
            @click="page = 'tasks'"
          >
            我的查询
          </button></template
        ><button
          v-if="isAdmin"
          :class="{ active: page === 'admin' }"
          @click="page = 'admin'"
        >
          管理工作台
        </button>
      </nav>
      <div class="user">
        {{ user.name || user.username
        }}<button @click="page = 'password'">改密</button
        ><button @click="logout">退出</button>
      </div>
    </header>
    <div v-if="notice" class="toast" role="status">
      {{ notice }}<button @click="notice = ''">×</button>
    </div>
    <main>
      <section
        v-if="page === 'query' && !user.must_change_pwd"
        class="workspace"
      >
        <aside class="panel">
          <h2>查询条件</h2>
          <p class="muted">圈选或点击站点添加小区</p>
          <div class="seg">
            <label v-for="n in ['local', 'other']" :key="n"
              ><input type="checkbox" :value="n" v-model="nets" />{{
                n === "local" ? "本网" : "异网"
              }}</label
            >
          </div>
          <label class="field-label"
            >查询月份（最多 {{ config?.max_months || 3 }} 个）</label
          >
          <div class="month-list">
            <label v-for="m in months" :key="m"
              ><input type="checkbox" :value="m" v-model="selectedMonths" />{{
                m
              }}</label
            >
            <p v-if="!months.length" class="muted">暂无可用月份</p>
          </div>
          <textarea
            v-model="purpose"
            maxlength="500"
            placeholder="请输入查询事由"
          ></textarea>
          <div class="selection-head">
            <b>已选 {{ cells.length }} 小区</b
            ><button @click="cells = []">清空</button>
          </div>
          <div class="chips">
            <span v-for="c in cells" :key="`${c.lac}-${c.cell_id}`"
              >{{ c.station_name || `${c.lac}/${c.cell_id}`
              }}<b @click="cells = cells.filter((x) => x !== c)">×</b></span
            >
            <p v-if="!cells.length" class="muted">尚未选择小区</p>
          </div>
          <button
            class="primary"
            :disabled="
              busy ||
              cells.length > (config?.max_cells || 2000) ||
              selectedMonths.length > (config?.max_months || 3)
            "
            @click="submit"
          >
            {{ busy ? "提交中…" : "开始查询" }}
          </button>
        </aside>
        <MapPane
          v-if="config"
          :config="config"
          @selected="select"
          @error="notice = $event"
        />
      </section>
      <section v-else-if="page === 'tasks'" class="content">
        <div class="toolbar">
          <h1>我的查询</h1>
          <button @click="loadTasks">刷新</button>
        </div>
        <div class="scroll-table">
          <table>
            <thead>
              <tr>
                <th>创建时间</th>
                <th>状态</th>
                <th>小区</th>
                <th>月份</th>
                <th>事由</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in tasks" :key="t.id">
                <td>{{ new Date(t.created_at).toLocaleString() }}</td>
                <td>
                  <span class="badge">{{ statusName(t.status) }}</span>
                </td>
                <td>{{ t.cell_keys.length }}</td>
                <td>{{ t.months.join("、") }}</td>
                <td>{{ t.purpose }}</td>
                <td class="actions">
                  <button @click="openTask(t)">查看</button
                  ><button @click="reuse(t)">复用</button
                  ><button
                    v-if="['PENDING', 'RUNNING'].includes(t.status)"
                    @click="cancel(t)"
                  >
                    取消
                  </button>
                </td>
              </tr>
              <tr v-if="!tasks.length">
                <td colspan="6" class="empty">暂无查询记录</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
      <section v-else-if="page === 'result'" class="content">
        <div class="toolbar">
          <button @click="page = 'tasks'">← 返回</button>
          <h1>查询结果</h1>
          <button v-if="isRunning" @click="cancel()">取消任务</button
          ><button
            :disabled="busy || isRunning || current?.status !== 'SUCCESS'"
            @click="exportXlsx"
          >
            {{ busy ? "正在导出…" : "导出 XLSX" }}</button
          ><label
            ><input
              type="checkbox"
              v-model="plain"
              :disabled="(!isAdmin && !user.view_plain) || isRunning"
            />显示明文</label
          >
        </div>
        <div class="status-card">
          <span class="badge">{{ statusName(current?.status || "") }}</span
          ><span v-if="isRunning"
            >批次 {{ current?.completed_batches }} /
            {{ current?.total_batches }} · 已读取
            {{
              (current?.rows_local || 0) + (current?.rows_other || 0)
            }}
            行</span
          ><span v-if="current?.error" class="error">{{ current.error }}</span>
          <p class="muted">
            {{ current?.purpose }} · 结果有效期
            {{
              current?.expire_at
                ? new Date(current.expire_at).toLocaleString()
                : "—"
            }}
          </p>
        </div>
        <div class="stats">
          <span
            >本网 <b>{{ current?.rows_local || 0 }}</b> 行 /
            {{ current?.uniq_local || 0 }} 号码</span
          ><span
            >异网 <b>{{ current?.rows_other || 0 }}</b> 行 /
            {{ current?.uniq_other || 0 }} 号码</span
          >
        </div>
        <div class="tabs">
          <button
            :class="{ active: rowNet === 'local' }"
            @click="rowNet = 'local'"
          >
            本网</button
          ><button
            :class="{ active: rowNet === 'other' }"
            @click="rowNet = 'other'"
          >
            异网
          </button>
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
                  {{ isRunning ? "正在查询，请稍候…" : "暂无可展示结果" }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="pagination">
          <span>共 {{ total }} 行</span
          ><select v-model="size">
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
        <h1>{{ user.must_change_pwd ? "首次登录请修改密码" : "修改密码" }}</h1>
        <form @submit.prevent="changePwd">
          <input
            v-model="pwd.old_password"
            type="password"
            placeholder="当前密码"
            autocomplete="current-password"
            required
          /><input
            v-model="pwd.new_password"
            type="password"
            placeholder="新密码（至少 8 位）"
            minlength="8"
            autocomplete="new-password"
            required
          /><button class="primary" :disabled="busy">保存新密码</button>
        </form>
      </section>
      <AdminPane v-else-if="isAdmin" />
    </main>
  </div>
</template>
