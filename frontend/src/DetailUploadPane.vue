<script setup lang="ts">
import { ref } from "vue";
import { api, errorText } from "./api";
const network = ref("local"), busy = ref(false), message = ref("");
const batch = ref(""), preview = ref<any>(null), completed = ref(false);
async function upload(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  message.value = ""; preview.value = null; batch.value = ""; completed.value = false;
  if (file.size > 200 * 1024 * 1024) {
    message.value = "文件最大允许 200 MB"; input.value = ""; return;
  }
  busy.value = true;
  try {
    const data = new FormData(); data.append("file", file); data.append("network", network.value);
    batch.value = (await api.post("/admin/detail-import", data)).data.batch_id;
    message.value = "上传成功，请校验文件。";
  } catch (error) { message.value = errorText(error); }
  finally { busy.value = false; input.value = ""; }
}
async function validate() {
  busy.value = true; message.value = "";
  try {
    preview.value = (await api.post(`/admin/detail-import/${batch.value}/preview`)).data;
  } catch (error) { message.value = errorText(error); preview.value = null; }
  finally { busy.value = false; }
}
async function confirm() {
  busy.value = true; message.value = "";
  try {
    await api.post(`/admin/detail-import/${batch.value}/confirm`);
    completed.value = true; message.value = "明细已整批导入，可返回地图查询。";
  } catch (error) { message.value = errorText(error); }
  finally { busy.value = false; }
}
function reset() { batch.value = ""; preview.value = null; message.value = ""; completed.value = false; }
</script>
<template>
  <section :aria-busy="busy">
    <div class="section-title"><h2>上传用户明细</h2>
      <p class="muted">CSV / XLSX，最大 200 MB。一个文件可含多个月账期，只能包含一个网别。</p>
    </div>
    <p>列名：month_id、device_number、cell_name、street_name、lac、cell_id；本网另需 uid 列。</p>
    <p class="muted">月账期使用 YYYYMM。号码和 UID 请设为文本；XLSX 仅保留一个工作表。任何错误或已有月份均整批拒绝，不覆盖、不追加。</p>
    <div class="toolbar">
      <label>网别 <select v-model="network" :disabled="busy" @change="reset"><option value="local">本网</option><option value="other">异网</option></select></label>
      <label>选择文件 <input type="file" accept=".csv,.xlsx" :disabled="busy" @change="upload" /></label>
      <button :disabled="busy || !batch || completed" @click="validate">校验预览</button>
    </div>
    <p v-if="busy" role="status">正在处理，请保持当前页面，较大文件需要一些时间。</p>
    <p v-if="message" class="inline-message" role="status">{{ message }}</p>
    <div v-if="preview">
      <p>月账期：{{ preview.months.join('、') }} · 数据行数：{{ preview.rows.toLocaleString() }}</p>
      <p v-if="preview.existing_months.length" class="inline-message">已有数据的月份：{{ preview.existing_months.join('、') }}，整批拒绝。</p>
      <p v-if="preview.error_count">共 {{ preview.error_count }} 行错误，展示前 100 条。请修正文件后重新上传。</p>
      <div v-if="preview.errors.length" class="scroll-table"><table><thead><tr><th>行号</th><th>错误</th></tr></thead>
        <tbody><tr v-for="(error, i) in preview.errors" :key="i"><td>{{ error.row || '文件' }}</td><td>{{ error.message }}</td></tr></tbody>
      </table></div>
      <p v-if="preview.valid && !completed">校验通过。请确认以上网别、月份和行数后提交。</p>
      <button class="primary compact" :disabled="busy || !preview.valid || completed" @click="confirm">确认整批导入</button>
    </div>
  </section>
</template>
