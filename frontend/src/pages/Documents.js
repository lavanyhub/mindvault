 import React, { useState } from 'react';
import { Search, FileText, Zap } from 'lucide-react';
import { searchDocuments } from '../api';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await searchDocuments(query);
      setResults(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: '800px' }}>
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '28px', fontWeight: '700', color: '#e2e8f0' }}>Search Knowledge Base</h1>
        <p style={{ color: '#64748b', marginTop: '6px' }}>Semantic + keyword search across all your documents</p>
      </div>

      {/* Search input */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '32px' }}>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
          placeholder="Search your knowledge base..."
          style={{ flex: 1, fontSize: '16px', padding: '14px 18px' }}
        />
        <button className="btn-primary" onClick={handleSearch} disabled={loading}
          style={{ padding: '14px 24px' }}>
          {loading ? <div className="spinner" style={{ margin: 0 }} /> : <Search size={18} />}
        </button>
      </div>

      {/* Results */}
      {results && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Semantic Results */}
          {results.semantic_results?.length > 0 && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                <Zap size={16} color="#6366f1" />
                <h2 style={{ fontSize: '16px', fontWeight: '600', color: '#94a3b8' }}>
                  Semantic Results ({results.semantic_results.length})
                </h2>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {results.semantic_results.map((r, i) => (
                  <div key={i} className="card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <FileText size={14} color="#6366f1" />
                        <span style={{ fontSize: '13px', fontWeight: '600', color: '#818cf8' }}>{r.title}</span>
                      </div>
                      <span style={{
                        fontSize: '11px', padding: '2px 8px', borderRadius: '4px',
                        background: 'rgba(99,102,241,0.1)', color: '#6366f1'
                      }}>
                        {Math.round(r.score * 100)}% match
                      </span>
                    </div>
                    <p style={{ fontSize: '14px', color: '#94a3b8', lineHeight: '1.6' }}>{r.content}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Keyword Results */}
          {results.keyword_results?.length > 0 && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                <Search size={16} color="#f59e0b" />
                <h2 style={{ fontSize: '16px', fontWeight: '600', color: '#94a3b8' }}>
                  Keyword Results ({results.keyword_results.length})
                </h2>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {results.keyword_results.map((r, i) => (
                  <div key={i} className="card">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                      <FileText size={14} color="#f59e0b" />
                      <span style={{ fontSize: '13px', fontWeight: '600', color: '#fbbf24' }}>{r.title}</span>
                    </div>
                    {r.summary && <p style={{ fontSize: '14px', color: '#94a3b8', lineHeight: '1.6' }}>{r.summary}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {results.semantic_results?.length === 0 && results.keyword_results?.length === 0 && (
            <div style={{ textAlign: 'center', padding: '40px', color: '#334155' }}>
              <Search size={40} style={{ margin: '0 auto 12px', opacity: 0.3 }} />
              <p>No results found for "{query}"</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
