import axios from "axios";
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || "/api";
export const api = axios.create({ baseURL: apiBaseUrl, withCredentials: true });
let csrf = "";
export function setCsrf(v: string) {
  csrf = v;
}
api.interceptors.request.use((c) => {
  if (
    ["post", "patch", "put", "delete"].includes(
      (c.method || "").toLowerCase(),
    ) &&
    csrf
  )
    c.headers["X-CSRF-Token"] = csrf;
  return c;
});
api.interceptors.response.use(
  (r) => r,
  (e) => {
    if (e.response?.status === 401 && !e.config?.url?.includes("/auth/login"))
      window.dispatchEvent(new Event("bsq-session-expired"));
    return Promise.reject(e);
  },
);
export function errorText(e: unknown) {
  const x = e as any;
  return x?.response?.data?.message || x?.message || "请求失败";
}

export async function runOperation(kind: "preview" | "confirm" | "export" | "assemble", target: string, plain = false) {
  const { data: job } = await api.post("/operations", { kind, target, plain });
  for (let attempt = 0; attempt < 900; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 2000));
    const { data } = await api.get(`/operations/${job.id}`);
    if (data.status === "FAILED") throw new Error(data.message || "操作失败");
    if (data.status === "SUCCESS") {
      if (kind === "export") return (await api.get(`/operations/${job.id}/file`, { responseType: "blob" })).data;
      return data.result;
    }
  }
  throw new Error("等待操作超时，请检查任务状态后重试");
}

export async function uploadDetails(file: File, network: string) {
  const { data: upload } = await api.post("/admin/detail-uploads", {
    filename: file.name, network, size: file.size,
  });
  for (let offset = 0, part = 0; offset < file.size; offset += upload.part_size, part++) {
    await api.put(`/admin/detail-uploads/${upload.id}/parts/${part}`,
      file.slice(offset, offset + upload.part_size),
      { headers: { "Content-Type": "application/octet-stream" } });
  }
  return await runOperation("assemble", upload.id);
}
