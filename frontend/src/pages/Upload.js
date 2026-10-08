 import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, FileText, CheckCircle, AlertCircle, X } from 'lucide-react';
import { uploadDocument, streamJobStatus, getDocument } from '../api';

const STAGE_LABELS = {
  queued: 'Queued...',
  processing: 'Processing...',
  embedding: 'Embedding chunks...',
  summarizing: 'Generating summary, tags, action items...',
  saving: 'Saving results...',
  complete: 'Done',
};

export default function UploadPage({ onNavigate }) {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState('');
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const closeStreamRef = useRef(null);

  useEffect(() => () => closeStreamRef.current?.(), []);

  const onDrop = useCallback((accepted) => {
    if (accepted[0]) {
      setFile(accepted[0]);
      setTitle(accepted[0].name.replace(/\.[^/.]+$/, ''));
      setResult(null);
      setError(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': [], 'text/plain': [], 'text/markdown': [], 'application/json': [] },
    maxFiles: 1,
  });

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setProgress(0);
    setStage('uploading');
    setError(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', title || file.name);

    try {
      // UPGRADE (Phase 1.6): upload returns as soon as the file is saved
      // and chunked (job_id, no summary/tags yet) — then we subscribe to
      // /jobs/:id/stream for live per-stage progress instead of blocking.
      const res = await uploadDocument(formData, (pct) => {
        setProgress(Math.min(pct, 100));
      });
      const { job_id, doc_id } = res.data;
      setStage('processing');
      setProgress(100);

      closeStreamRef.current = streamJobStatus(job_id, {
        onUpdate: (job) => setStage(job.stage || job.status),
        onComplete: async (job) => {
          if (job.status === 'error') {
            setError(job.error || 'Processing failed.');
            setUploading(false);
            return;
          }
          try {
            const doc = await getDocument(doc_id);
            setResult(doc.data);
          } catch {
            setResult({ title, word_count: res.data.word_count, chunk_count: res.data.chunk_count });
          }
          setFile(null);
          setTitle('');
          setUploading(false);
        },
        onError: () => {
          setError('Lost connection while processing. Check the Documents page — it may still finish.');
          setUploading(false);
        },
      });
    } catch (err) {
      setError(err.response?.data?.error || 'Upload failed. Please try again.');
      setUploading(false);
    }
  };

  return (
    <div style={{ maxWidth: '700px' }}>
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '28px', fontWeight: '700', color: '#e2e8f0' }}>Upload Document</h1>
        <p style={{ color: '#64748b', marginTop: '6px' }}>Add documents to your knowledge base</p>
      </div>

      {/* Dropzone */}
      <div {...getRootProps()} style={{
        border: `2px dashed ${isDragActive ? '#6366f1' : 'rgba(255,255,255,0.1)'}`,
        borderRadius: '12px', padding: '48px',
        textAlign: 'center', cursor: 'pointer',
        background: isDragActive ? 'rgba(99,102,241,0.05)' : 'rgba(255,255,255,0.02)',
        transition: 'all 0.2s', marginBottom: '20px'
      }}>
        <input {...getInputProps()} />
        <Upload size={40} color={isDragActive ? '#6366f1' : '#334155'} style={{ margin: '0 auto 16px' }} />
        <p style={{ color: '#94a3b8', fontSize: '16px', marginBottom: '8px' }}>
          {isDragActive ? 'Drop your file here' : 'Drag & drop or click to upload'}
        </p>
        <p style={{ color: '#475569', fontSize: '13px' }}>PDF, TXT, Markdown, JSON · Max 50MB</p>
      </div>

      {/* Selected file */}
      {file && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '12px',
          padding: '14px 16px', background: 'rgba(99,102,241,0.1)',
          borderRadius: '8px', border: '1px solid rgba(99,102,241,0.2)',
          marginBottom: '16px'
        }}>
          <FileText size={18} color="#6366f1" />
          <span style={{ flex: 1, fontSize: '14px', color: '#e2e8f0' }}>{file.name}</span>
          <span style={{ fontSize: '12px', color: '#64748b' }}>
            {(file.size / 1024 / 1024).toFixed(2)} MB
          </span>
          <button onClick={() => setFile(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b' }}>
            <X size={16} />
          </button>
        </div>
      )}

      {/* Title input */}
      {file && (
        <div style={{ marginBottom: '20px' }}>
          <label style={{ fontSize: '13px', color: '#94a3b8', marginBottom: '8px', display: 'block' }}>
            Document Title
          </label>
          <input
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Enter a title for this document"
          />
        </div>
      )}

      {/* Progress */}
      {uploading && (
        <div style={{ marginBottom: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <span style={{ fontSize: '13px', color: '#94a3b8' }}>
              {progress < 100 ? 'Uploading...' : `🤖 ${STAGE_LABELS[stage] || 'Processing...'}`}
            </span>
            <span style={{ fontSize: '13px', color: '#6366f1' }}>{progress}%</span>
          </div>
          <div style={{ height: '4px', background: 'rgba(255,255,255,0.05)', borderRadius: '2px' }}>
            <div style={{
              height: '100%', width: `${progress}%`,
              background: 'linear-gradient(90deg, #6366f1, #8b5cf6)',
              borderRadius: '2px', transition: 'width 0.3s'
            }} />
          </div>
          {progress === 100 && (
            <p style={{ fontSize: '12px', color: '#64748b', marginTop: '8px' }}>
              {/* UPGRADE: this used to be a static guess ("1-2 minutes") shown
                  the whole time. Now it reflects the real stage from the SSE
                  job stream. */}
              Live status — no need to keep this tab frozen while it runs.
            </p>
          )}
        </div>
      )}

      {/* Error */}
      {error && <div className="error" style={{ marginBottom: '16px' }}>{error}</div>}

      {/* Success */}
      {result && (
        <div style={{
          background: 'rgba(34,197,94,0.05)', border: '1px solid rgba(34,197,94,0.2)',
          borderRadius: '12px', padding: '20px', marginBottom: '20px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <CheckCircle size={20} color="#22c55e" />
            <span style={{ color: '#4ade80', fontWeight: '600' }}>Document processed successfully!</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
            {[
              ['Words', result.word_count?.toLocaleString()],
              ['Chunks', result.chunk_count],
            ].map(([k, v]) => (
              <div key={k} style={{ background: 'rgba(255,255,255,0.03)', borderRadius: '8px', padding: '12px' }}>
                <div style={{ fontSize: '20px', fontWeight: '700', color: '#e2e8f0' }}>{v}</div>
                <div style={{ fontSize: '12px', color: '#64748b' }}>{k}</div>
              </div>
            ))}
          </div>
          {result.summary && (
            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '13px', color: '#64748b', marginBottom: '6px' }}>AI Summary</div>
              <p style={{ fontSize: '14px', color: '#94a3b8', lineHeight: '1.6' }}>{result.summary}</p>
            </div>
          )}
          {result.tags?.length > 0 && (
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {/* FIX: result now comes from GET /documents/:id (Phase 1.6),
                  whose tags are {id, name, color} objects, not bare strings
                  like the old synchronous upload response used to return. */}
              {result.tags.map(t => (
                <span key={t.id ?? t.name} className="tag">{t.name ?? t}</span>
              ))}
            </div>
          )}
          <button className="btn-primary" onClick={() => onNavigate('query')} style={{ marginTop: '16px' }}>
            Ask Questions About This →
          </button>
        </div>
      )}

      {/* Upload button */}
      {file && !uploading && !result && (
        <button className="btn-primary" onClick={handleUpload} style={{ width: '100%', padding: '14px' }}>
          Upload & Process with AI
        </button>
      )}
    </div>
  );
}
