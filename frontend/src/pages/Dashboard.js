 import React, { useEffect, useState } from 'react';
import { Brain, FileText, MessageSquare, Tag, CheckSquare, TrendingUp } from 'lucide-react';
import { getAnalytics } from '../api';

const StatCard = ({ icon: Icon, label, value, color }) => (
  <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
    <div style={{
      width: '48px', height: '48px', borderRadius: '12px',
      background: `${color}20`, display: 'flex',
      alignItems: 'center', justifyContent: 'center', flexShrink: 0
    }}>
      <Icon size={22} color={color} />
    </div>
    <div>
      <div style={{ fontSize: '28px', fontWeight: '700', color: '#e2e8f0' }}>{value}</div>
      <div style={{ fontSize: '13px', color: '#64748b', marginTop: '2px' }}>{label}</div>
    </div>
  </div>
);

export default function Dashboard({ onNavigate }) {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAnalytics()
      .then(r => setAnalytics(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="loading"><div className="spinner" />Loading...</div>
  );

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '28px', fontWeight: '700', color: '#e2e8f0' }}>
          Welcome to MindVault 🧠
        </h1>
        <p style={{ color: '#64748b', marginTop: '6px' }}>
          Your personal AI knowledge base
        </p>
      </div>

      {/* Stats Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gap: '16px', marginBottom: '32px'
      }}>
        <StatCard icon={FileText} label="Documents" value={analytics?.total_documents ?? 0} color="#6366f1" />
        <StatCard icon={Brain} label="Knowledge Chunks" value={analytics?.total_chunks ?? 0} color="#8b5cf6" />
        <StatCard icon={MessageSquare} label="Queries Asked" value={analytics?.total_queries ?? 0} color="#06b6d4" />
        <StatCard icon={Tag} label="Tags" value={analytics?.total_tags ?? 0} color="#f59e0b" />
        <StatCard icon={CheckSquare} label="Pending Actions" value={analytics?.pending_actions ?? 0} color="#ef4444" />
        <StatCard icon={TrendingUp} label="Total Words" value={(analytics?.total_words ?? 0).toLocaleString()} color="#22c55e" />
      </div>

      {/* Recent Documents */}
      <div className="glass" style={{ padding: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h2 style={{ fontSize: '18px', fontWeight: '600', color: '#e2e8f0' }}>Recent Documents</h2>
          <button className="btn-secondary" onClick={() => onNavigate('upload')} style={{ fontSize: '13px', padding: '8px 16px' }}>
            + Add Document
          </button>
        </div>

        {analytics?.recent_documents?.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px', color: '#334155' }}>
            <Brain size={40} style={{ margin: '0 auto 12px', opacity: 0.3 }} />
            <p>No documents yet. Upload your first document to get started.</p>
            <button className="btn-primary" onClick={() => onNavigate('upload')} style={{ marginTop: '16px' }}>
              Upload Document
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {analytics.recent_documents.map((doc, i) => (
              <div key={i} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '12px 16px', background: 'rgba(255,255,255,0.03)',
                borderRadius: '8px', border: '1px solid rgba(255,255,255,0.06)'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <FileText size={16} color="#6366f1" />
                  <span style={{ fontSize: '14px', color: '#e2e8f0' }}>{doc.title}</span>
                </div>
                <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                  <span style={{ fontSize: '12px', color: '#475569' }}>{doc.word_count?.toLocaleString()} words</span>
                  <span style={{ fontSize: '12px', color: '#334155' }}>
                    {new Date(doc.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
