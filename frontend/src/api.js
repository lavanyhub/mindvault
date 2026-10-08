 import axios from 'axios';

const BASE_URL = 'http://127.0.0.1:8080/api';

const API = axios.create({
  baseURL: BASE_URL,
  timeout: 300000,
});

// UPGRADE (Phase 1.6): upload now returns a job_id immediately (202) instead
// of blocking until embedding + summarization finish. onUploadProgress only
// covers the file transfer itself — actual processing progress comes from
// streamJobStatus below.
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

/**
 * Subscribe to ingestion progress for one upload job via SSE.
 *
 * callbacks: { onUpdate(job), onComplete(job), onError(err) }
 * Returns a close() function — call it on unmount to avoid leaking the
 * EventSource connection.
 */
export function streamJobStatus(jobId, { onUpdate, onComplete, onError } = {}) {
  const source = new EventSource(`${BASE_URL}/jobs/${jobId}/stream`);

  source.onmessage = (e) => {
    const job = JSON.parse(e.data);
    onUpdate?.(job);
    if (job.status === 'complete' || job.status === 'error') {
      source.close();
      onComplete?.(job);
    }
  };

  source.onerror = (e) => {
    onError?.(e);
    source.close();
  };

  return () => source.close();
}

/**
 * Ask a question and stream the answer token-by-token via SSE.
 *
 * callbacks: { onSources({sources, context_used}), onToken(token), onDone({answer}), onError(err) }
 * Returns a close() function.
 *
 * Uses fetch + a manual SSE parser rather than EventSource because
 * EventSource only supports GET; this endpoint needs a JSON POST body.
 */
export function streamQuery(question, { onSources, onToken, onDone, onError } = {}) {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${BASE_URL}/query/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        throw new Error(`Query stream failed: ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE events are separated by a blank line; each event has an
        // "event: <name>" line and a "data: <json>" line.
        const events = buffer.split('\n\n');
        buffer = events.pop(); // last chunk may be incomplete, keep it

        for (const raw of events) {
          const eventLine = raw.split('\n').find(l => l.startsWith('event:'));
          const dataLine = raw.split('\n').find(l => l.startsWith('data:'));
          if (!dataLine) continue;

          const eventName = eventLine ? eventLine.slice('event:'.length).trim() : 'message';
          const data = JSON.parse(dataLine.slice('data:'.length).trim());

          if (eventName === 'sources') onSources?.(data);
          else if (eventName === 'token') onToken?.(data.token);
          else if (eventName === 'done') onDone?.(data);
          else if (eventName === 'error') onError?.(data);
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') onError?.(err);
    }
  })();

  return () => controller.abort();
}
