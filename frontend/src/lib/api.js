import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const client = axios.create({ baseURL: API, withCredentials: true });

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("if_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && !window.location.pathname.includes("/login")) {
      localStorage.removeItem("if_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export function formatApiErrorDetail(detail) {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).filter(Boolean).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

// auth
export const login = (email, password) =>
  client.post("/auth/login", { email, password }).then((r) => r.data);
export const logout = () => client.post("/auth/logout").then((r) => r.data);
export const me = () => client.get("/auth/me").then((r) => r.data);
export const listUsers = () => client.get("/auth/users").then((r) => r.data);
export const createUser = (data) => client.post("/auth/register", data).then((r) => r.data);
export const deleteUser = (id) => client.delete(`/auth/users/${id}`).then((r) => r.data);

// instances
export const getInstances = (search) =>
  client.get("/instances", { params: search ? { search } : {} }).then((r) => r.data);
export const getInstance = (id) => client.get(`/instances/${id}`).then((r) => r.data);
export const createInstance = (data) => client.post("/instances", data).then((r) => r.data);
export const updateInstance = (id, data) => client.put(`/instances/${id}`, data).then((r) => r.data);
export const deleteInstance = (id) => client.delete(`/instances/${id}`).then((r) => r.data);
export const deleteAllInstances = () =>
  client.delete("/instances", { params: { confirm: "DELETE_ALL" } }).then((r) => r.data);
export const getStats = () => client.get("/stats").then((r) => r.data);

export const importCsv = (file) => {
  const fd = new FormData();
  fd.append("file", file);
  return client
    .post("/instances/import-csv", fd, { headers: { "Content-Type": "multipart/form-data" } })
    .then((r) => r.data);
};

export const exportCsvUrl = `${API}/instances/export`;
export const downloadCsv = async () => {
  const res = await client.get("/instances/export", { responseType: "blob" });
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = "infra_inventory.csv";
  a.click();
  URL.revokeObjectURL(url);
};

export const generateTerraform = (payload) =>
  client.post("/terraform/generate", payload).then((r) => r.data);

// k8s clusters
export const listClusters = () => client.get("/k8s/clusters").then((r) => r.data);
export const createCluster = (data) => client.post("/k8s/clusters", data).then((r) => r.data);
export const updateCluster = (id, data) => client.put(`/k8s/clusters/${id}`, data).then((r) => r.data);
export const deleteCluster = (id) => client.delete(`/k8s/clusters/${id}`).then((r) => r.data);
export const previewCluster = (data) => client.post("/k8s/preview", data).then((r) => r.data);

export default client;
