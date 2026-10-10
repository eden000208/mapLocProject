export type User = {
  id: number;
  username: string;
  name: string;
  role: "admin" | "analyst";
  is_active: boolean;
  view_plain: boolean;
  districts: string[];
  service_centers: string[];
  must_change_pwd: boolean;
  csrf_token?: string;
};
export type Cell = {
  lac: string | number;
  cell_id: string | number;
  station_name?: string;
  district?: string;
  service_center?: string;
  lng?: number;
  lat?: number;
};
export type Task = {
  id: string;
  status: string;
  cell_keys: Cell[];
  months: string[];
  nets: string[];
  purpose: string;
  rows_local: number;
  rows_other: number;
  uniq_local: number;
  uniq_other: number;
  completed_batches: number;
  total_batches: number;
  error?: string;
  created_at: string;
  expire_at: string;
};
