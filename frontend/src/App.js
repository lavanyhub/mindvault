 import React, { useState } from 'react';
import { Brain, Upload, Search, MessageSquare, FileText, Menu, X } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import UploadPage from './pages/Upload';
import SearchPage from './pages/Search';
import QueryPage from './pages/Query';
import DocumentsPage from './pages/Documents';
import './index.css';

const navItems = [
  { id: 'dashboard', label: 'Dashboard', icon: Brain },
  { id: 'upload', label: 'Upload', icon: Upload },
  { id: 'documents', label: 'Documents', icon: FileText },
  { id: 'search', label: 'Search', icon: Search },
  { id: 'query', label: 'Ask AI', icon: MessageSquare },
];

export default function App() {
  const [page, setPage] = useState('dashboard');
  const [menuOpen, setMenuOpen] = useState(false);

  const pages = {
    dashboard: <Dashboard onNavigate={setPage} />,
    upload: <UploadPage onNavigate={setPage} />,
    documents: <DocumentsPage />,
    search: <SearchPage />,
    query: <QueryPage />,
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Sidebar */}
      <aside style={{
        width: '240px',
        background: 'rgba(255,255,255,0.02)',
        borderRight: '1px solid rgba(255,255,255,0.06)',
        display: 'flex',
        flexDirection: 'column',
        padding: '24px 16px',
        position: 'fixed',
        height: '100vh',
        zIndex: 100,
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '40px', padding: '0 8px' }}>
          <div style={{
            width: '36px', height: '36px',
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            borderRadius: '10px',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <Brain size={20} color="white" />
          </div>
          <div>
            <div style={{ fontWeight: '700', fontSize: '16px', color: '#e2e8f0' }}>MindVault</div>
            <div style={{ fontSize: '11px', color: '#64748b' }}>Knowledge OS</div>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {navItems.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setPage(id)} style={{
              display: 'flex', alignItems: 'center', gap: '10px',
              padding: '10px 12px', borderRadius: '8px', border: 'none',
              cursor: 'pointer', fontSize: '14px', fontWeight: '500',
              background: page === id ? 'rgba(99,102,241,0.15)' : 'transparent',
              color: page === id ? '#818cf8' : '#94a3b8',
              transition: 'all 0.2s', textAlign: 'left',
            }}>
              <Icon size={18} />
              {label}
            </button>
          ))}
        </nav>

        {/* Footer */}
        <div style={{ marginTop: 'auto', padding: '8px', fontSize: '12px', color: '#334155' }}>
          MindVault v1.0 · Local AI
        </div>
      </aside>

      {/* Main content */}
      <main style={{ marginLeft: '240px', flex: 1, padding: '32px', minHeight: '100vh' }}>
        {pages[page]}
      </main>
    </div>
  );
}
