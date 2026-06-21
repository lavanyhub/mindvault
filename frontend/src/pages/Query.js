 import React, { useState, useRef, useEffect } from 'react';
import { Send, Brain, FileText, Loader } from 'lucide-react';
import { queryKnowledge } from '../api';

export default function QueryPage() {
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleQuery = async () => {
    if (!question.trim() || loading) return;
    const q = question.trim();
    setQuestion('');
    setMessages(prev => [...prev, { type: 'user', content: q }]);
    setLoading(true);

    try {
      const res = await queryKnowledge(q);
      setMessages(prev => [...prev, {
        type: 'assistant',
        content: res.data.answer,
        sources: res.data.sources,
        context: res.data.context_used
      }]);
    } catch {
      setMessages(prev => [...prev, {
        type: 'assistant',
        content: 'Sorry, something went wrong. Make sure Ollama is running.',
        sources: []
      }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: '800px', height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '28px', fontWeight: '700', color: '#e2e8f0' }}>Ask Your Knowledge Base</h1>
        <p style={{ color: '#64748b', marginTop: '6px' }}>Ask anything — MindVault searches your documents and answers</p>
      </div>

      {/* Messages */}
      <div style={{
        flex: 1, overflowY: 'auto', display: 'flex',
        flexDirection: 'column', gap: '16px', marginBottom: '16px'
      }}>
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: '#334155' }}>
            <Brain size={48} style={{ margin: '0 auto 16px', opacity: 0.3 }} />
            <p style={{ fontSize: '16px', marginBottom: '8px' }}>Ask anything about your documents</p>
            <p style={{ fontSize: '13px' }}>Try: "What did I learn about X?" or "Summarize my notes on Y"</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} style={{
            display: 'flex', justifyContent: msg.type === 'user' ? 'flex-end' : 'flex-start'
          }}>
            {msg.type === 'assistant' && (
              <div style={{
                width: '32px', height: '32px', borderRadius: '50%',
                background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0, marginRight: '10px', marginTop: '4px'
              }}>
                <Brain size={16} color="white" />
              </div>
            )}
            <div style={{ maxWidth: '80%' }}>
              <div style={{
                padding: '12px 16px', borderRadius: '12px',
                background: msg.type === 'user'
                  ? 'linear-gradient(135deg, #6366f1, #8b5cf6)'
                  : 'rgba(255,255,255,0.05)',
                border: msg.type === 'assistant' ? '1px solid rgba(255,255,255,0.08)' : 'none',
                color: '#e2e8f0', fontSize: '14px', lineHeight: '1.6'
              }}>
                {msg.content}
              </div>
              {msg.sources?.length > 0 && (
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '8px' }}>
                  {msg.sources.map(s => (
                    <span key={s} style={{
                      display: 'flex', alignItems: 'center', gap: '4px',
                      fontSize: '11px', color: '#6366f1',
                      background: 'rgba(99,102,241,0.1)',
                      padding: '3px 8px', borderRadius: '4px'
                    }}>
                      <FileText size={10} /> {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '32px', height: '32px', borderRadius: '50%',
              background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              <Brain size={16} color="white" />
            </div>
            <div style={{
              padding: '12px 16px', borderRadius: '12px',
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(255,255,255,0.08)',
              display: 'flex', alignItems: 'center', gap: '8px', color: '#64748b', fontSize: '14px'
            }}>
              <Loader size={14} className="spinner" style={{ animation: 'spin 0.8s linear infinite' }} />
              Searching your knowledge base...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ display: 'flex', gap: '10px' }}>
        <input
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleQuery()}
          placeholder="Ask anything about your documents..."
          style={{ flex: 1 }}
        />
        <button className="btn-primary" onClick={handleQuery} disabled={loading || !question.trim()}
          style={{ padding: '10px 16px', opacity: loading || !question.trim() ? 0.5 : 1 }}>
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}
