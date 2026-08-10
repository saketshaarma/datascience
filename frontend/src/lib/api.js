import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const client = axios.create({ baseURL: API });

export const getInstances = (search) =>
  client.get("/instances", { params: search ? { search } : {} }).then((r) => r.data);

export const getInstance = (id) => client.get(`/instances/${id}`).then((r) => r.data);

export const createInstance = (data) => client.post("/instances", data).then((r) => r.data);

export const updateInstance = (id, data) =>
  client.put(`/instances/${id}`, data).then((r) => r.data);

export const deleteInstance = (id) => client.delete(`/instances/${id}`).then((r) => r.data);

export const getStats = () => client.get("/stats").then((r) => r.data);

export const importCsv = (file) => {
  const fd = new FormData();
  fd.append("file", file);
  return client
    .post("/instances/import-csv", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data);
};

export const generateTerraform = (payload) =>
  client.post("/terraform/generate", payload).then((r) => r.data);

export default client;
