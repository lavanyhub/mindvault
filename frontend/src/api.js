 import axios from 'axios';

const API = axios.create({
  baseURL: 'http://127.0.0.1:8080/api',
  timeout: 60000,
});

export const uploadDocument = (formData, onProgress) =>
  API.post('/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => onProgress(Math.round((e.loaded * 100) / e.total)),
  });

export const getDocuments = () => API.get('/documents');
export const getDocument = (id) => API.get(`/documents/${id}`);
export const deleteDocument = (id) => API.delete(`/documents/${id}`);
export const searchDocuments = (query) => API.post('/search', { query });
export const queryKnowledge = (question) => API.post('/query', { question });
export const getTags = () => API.get('/tags');
export const getHistory = () => API.get('/history');
export const getAnalytics = () => API.get('/analytics');
