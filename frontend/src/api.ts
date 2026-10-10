import axios from "axios";
export const api = axios.create({ baseURL: "/api", withCredentials: true });
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
