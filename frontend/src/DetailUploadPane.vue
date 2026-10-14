<script setup lang="ts">
import { ref } from "vue";
import { api, errorText } from "./api";
import { UploadCloud, FileCheck2, CheckCircle2, Info } from "lucide-vue-next";
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
  <section class="detail-import" :aria-busy="busy" aria-labelledby="detail-import-title">
    <div class="section-title"><h2 id="detail-import-title">上传用户明细</h2>
      <p class="muted">一个文件可含多个月账期，按网别上传，校验通过后整批导入。</p>
    </div>
    <div class="steps detail-steps" aria-label="用户明细导入流程">
      <span :class="{ active: !batch, complete: !!batch }" :aria-current="!batch ? 'step' : undefined"><b>1</b>上传文件</span>
      <span :class="{ active: !!batch && !preview?.valid, complete: !!preview?.valid }" :aria-current="batch && !preview?.valid ? 'step' : undefined"><b>2</b>全量校验预览</span>
      <span :class="{ active: !!preview?.valid && !completed, complete: completed }" :aria-current="preview?.valid && !completed ? 'step' : undefined"><b>3</b>{{ completed ? '导入完成' : '确认整批导入' }}</span>
    </div>
    <div class="detail-setup">
      <div class="detail-workspace">
        <label class="detail-network">文件网别
          <select v-model="network" :disabled="busy" @change="reset" aria-describedby="detail-network-help"><option value="local">本网</option><option value="other">异网</option></select>
        </label>
        <p id="detail-network-help" class="field-help">一个文件只能包含一个网别，切换网别后需重新上传。</p>
        <div class="upload detail-upload">
          <UploadCloud :size="32" aria-hidden="true" />
          <h3>选择用户明细文件</h3>
          <p class="muted">支持 CSV / XLSX，文件最大 200 MB。</p>
          <input type="file" accept=".csv,.xlsx" aria-label="选择用户明细 CSV 或 XLSX 文件" :disabled="busy" @change="upload" />
        </div>
        <div class="detail-upload-actions">
          <p class="field-help">{{ completed ? '本批次已导入，可选择新文件继续上传。' : batch ? '文件已上传，继续校验全部数据。' : '上传后进行全量校验，确认前不会写入明细。' }}</p>
          <button class="primary compact" :disabled="busy || !batch || completed" @click="validate"><FileCheck2 :size="16" aria-hidden="true" />校验预览</button>
        </div>
      </div>
      <aside class="detail-guidance" aria-labelledby="detail-format-title">
        <h3 id="detail-format-title">文件规范</h3>
        <p class="muted">请使用以下列名，本网另需 <code>uid</code> 列。</p>
        <dl class="detail-fields">
          <div><dt>月账期</dt><dd><code>month_id</code></dd></div>
          <div><dt>号码</dt><dd><code>device_number</code></dd></div>
          <div><dt>小区名称</dt><dd><code>cell_name</code></dd></div>
          <div><dt>街道名称</dt><dd><code>street_name</code></dd></div>
          <div><dt>位置区码</dt><dd><code>lac</code></dd></div>
          <div><dt>小区标识</dt><dd><code>cell_id</code></dd></div>
          <div class="detail-local-field"><dt>用户标识 <span>仅本网</span></dt><dd><code>uid</code></dd></div>
        </dl>
        <ul class="detail-rules">
          <li>月账期使用 YYYYMM。</li>
          <li>号码和 UID 请设为文本。</li>
          <li>XLSX 仅保留一个工作表。</li>
        </ul>
        <p class="detail-policy"><Info :size="16" aria-hidden="true" /><span>任何错误或已有月份均整批拒绝，不覆盖、不追加。</span></p>
      </aside>
    </div>
    <p v-if="busy" class="detail-processing" role="status">正在处理，请保持当前页面，较大文件需要一些时间。</p>
    <p v-if="message" class="inline-message detail-message" :class="{ 'detail-message-complete': completed }" role="status">{{ message }}</p>
    <div v-if="preview" class="detail-preview" aria-labelledby="detail-preview-title">
      <div class="detail-preview-heading">
        <h3 id="detail-preview-title"><FileCheck2 :size="18" aria-hidden="true" />全量校验结果</h3>
        <span class="badge" :data-status="preview.valid ? 'SUCCESS' : 'FAILED'">{{ preview.valid ? '校验通过' : '校验未通过' }}</span>
      </div>
      <dl class="detail-summary">
        <div><dt>网别</dt><dd>{{ network === 'local' ? '本网' : '异网' }}</dd></div>
        <div><dt>月账期</dt><dd>{{ preview.months.join('、') }}</dd></div>
        <div><dt>数据行数</dt><dd>{{ preview.rows.toLocaleString() }}</dd></div>
      </dl>
      <p v-if="preview.existing_months.length" class="inline-message">已有数据的月份：{{ preview.existing_months.join('、') }}，整批拒绝。</p>
      <p v-if="preview.error_count" class="detail-error-note">共 {{ preview.error_count }} 行错误，展示前 100 条。请修正文件后重新上传。</p>
      <div v-if="preview.errors.length" class="scroll-table detail-errors"><table><thead><tr><th scope="col">行号</th><th scope="col">错误</th></tr></thead>
        <tbody><tr v-for="(error, i) in preview.errors" :key="i"><td>{{ error.row || '文件' }}</td><td>{{ error.message }}</td></tr></tbody>
      </table></div>
      <div class="detail-confirm">
        <p v-if="preview.valid && !completed"><CheckCircle2 :size="17" aria-hidden="true" />校验通过。请确认以上网别、月份和行数后提交。</p>
        <p v-else class="muted">{{ completed ? '明细已整批导入，可返回地图查询。' : '请修正文件后重新上传，校验通过后才能导入。' }}</p>
        <button class="primary compact" :disabled="busy || !preview.valid || completed" @click="confirm">确认整批导入</button>
      </div>
    </div>
  </section>
</template>
<style scoped>
.detail-import { max-width: 82rem; }
.detail-steps { margin-top: 1.5rem; }
.detail-setup { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(18rem, 1fr); gap: clamp(1.5rem, 3vw, 3rem); }
.detail-workspace, .detail-guidance { min-width: 0; }
.detail-network { display: flex; align-items: center; gap: 1rem; font-size: 0.9286rem; font-weight: 600; }
.detail-network select { min-width: 10rem; font-weight: 400; }
.detail-workspace > .field-help { margin: 0.65rem 0 1.2rem; }
.detail-upload { min-height: 17.5rem; padding: 2.5rem 1.5rem; gap: 0.85rem; }
.detail-upload input { margin-top: 0.5rem; }
.detail-upload-actions { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-top: 1rem; }
.detail-upload-actions p { margin: 0; max-width: 26rem; }
.detail-upload-actions button { flex-shrink: 0; }
.detail-guidance { border-left: 1px solid var(--line); padding-left: clamp(1.5rem, 3vw, 3rem); }
.detail-guidance h3 { margin: 0 0 0.5rem; }
.detail-guidance > .muted { margin-bottom: 1rem; }
.detail-fields { margin: 0; font-size: 0.8571rem; }
.detail-fields > div { display: flex; justify-content: space-between; gap: 1rem; padding: 0.5rem 0; border-bottom: 1px solid #eeece5; }
.detail-fields dt { color: var(--muted); }
.detail-fields dd { margin: 0; }
.detail-fields dt span { font-size: 0.7857rem; margin-left: 0.3rem; color: var(--accent); }
.detail-import code { font: inherit; overflow-wrap: anywhere; }
.detail-rules { margin: 1rem 0; padding-left: 1.15rem; color: var(--muted); font-size: 0.8571rem; line-height: 1.9; }
.detail-policy { display: flex; align-items: flex-start; gap: 0.55rem; margin: 0; color: var(--muted); font-size: 0.8571rem; line-height: 1.8; }
.detail-policy svg { flex-shrink: 0; margin-top: 0.2rem; color: var(--accent); }
.detail-processing { margin: 1.25rem 0 0; color: var(--muted); font-size: 0.9286rem; }
.detail-message { margin: 1.25rem 0 0; overflow-wrap: anywhere; }
.detail-message-complete { color: var(--green); background: #eef2e9; }
.detail-preview { margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid var(--line); }
.detail-preview-heading { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.detail-preview-heading h3 { display: flex; align-items: center; gap: 0.6rem; margin: 0; font-size: 1.0714rem; }
.detail-preview-heading h3 svg { color: var(--muted); }
.detail-summary { display: grid; grid-template-columns: minmax(5rem, 0.7fr) minmax(0, 3fr) minmax(7rem, 1fr); gap: 1.5rem; margin: 1.5rem 0; }
.detail-summary > div { min-width: 0; }
.detail-summary dt { color: var(--muted); font-size: 0.8571rem; margin-bottom: 0.5rem; }
.detail-summary dd { margin: 0; font-size: 1rem; font-weight: 500; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.detail-error-note { color: #a24b3e; font-size: 0.9286rem; }
.detail-errors { max-height: 24rem; overflow-y: auto; }
.detail-errors table { min-width: 0; }
.detail-errors th:first-child, .detail-errors td:first-child { width: 5rem; white-space: nowrap; }
.detail-errors th, .detail-errors td { padding: 0.85rem 1rem; }
.detail-errors th { position: sticky; top: 0; }
.detail-confirm { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem; border-top: 1px solid var(--line); padding-top: 1.25rem; margin-top: 1.5rem; }
.detail-confirm p { display: flex; align-items: center; gap: 0.55rem; margin: 0; font-size: 0.9286rem; }
.detail-confirm p svg { flex-shrink: 0; color: var(--green); }
@media (max-width: 1100px) {
  .detail-setup { grid-template-columns: minmax(0, 1fr) minmax(16rem, 0.85fr); gap: 1.5rem; }
  .detail-guidance { padding-left: 1.5rem; }
  .detail-upload-actions { align-items: flex-start; flex-direction: column; }
}
@media (max-width: 760px) {
  .detail-setup { grid-template-columns: minmax(0, 1fr); gap: 1.75rem; }
  .detail-guidance { border-left: 0; border-top: 1px solid var(--line); padding: 1.25rem 0 0; }
  .detail-steps { margin-block: 1.25rem; }
  .detail-upload { min-height: 15rem; padding: 2rem 1rem; }
  .detail-upload-actions { gap: 0.8rem; }
  .detail-upload-actions button, .detail-confirm button { width: 100%; }
  .detail-summary { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 1.1rem; }
  .detail-summary > div:nth-child(2) { grid-column: 1 / -1; grid-row: 2; }
  .detail-preview-heading { align-items: flex-start; }
}
</style>
