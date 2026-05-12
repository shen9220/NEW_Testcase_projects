import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { Layout, Menu, Tag } from 'antd';
import { FileTextOutlined, ReadOutlined, HistoryOutlined } from '@ant-design/icons';
import { useState, useEffect } from 'react';
import Workbench from './pages/Workbench';
import LogCenter from './pages/LogCenter';
import History from './pages/History';
import api from './services/api';

const { Header, Content } = Layout;

export default function App() {
  const [supabaseStatus, setSupabaseStatus] = useState<'connected' | 'disconnected'>('disconnected');

  useEffect(() => {
    checkHealth();
  }, []);

  async function checkHealth() {
    try {
      const res = await api.get('/health');
      setSupabaseStatus(res.data?.supabase === 'connected' ? 'connected' : 'disconnected');
    } catch {
      setSupabaseStatus('disconnected');
    }
  }

  return (
    <BrowserRouter>
      <Layout style={{ minHeight: '100vh' }}>
        <Header className="app-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <span className="logo-text">AI 测试用例生成器</span>
            <Menu
              theme="dark"
              mode="horizontal"
              style={{ flex: 1, minWidth: 200 }}
              items={[
                { key: 'workbench', icon: <FileTextOutlined />, label: <NavLink to="/">工作台</NavLink> },
                { key: 'history', icon: <HistoryOutlined />, label: <NavLink to="/history">历史任务</NavLink> },
                { key: 'logs', icon: <ReadOutlined />, label: <NavLink to="/logs">日志中心</NavLink> },
              ]}
            />
          </div>
          <Tag color={supabaseStatus === 'connected' ? 'green' : 'red'}>
            {supabaseStatus === 'connected' ? 'Supabase 已连接' : '离线模式'}
          </Tag>
        </Header>
        <Content>
          <Routes>
            <Route path="/" element={<Workbench />} />
            <Route path="/history" element={<History />} />
            <Route path="/logs" element={<LogCenter />} />
          </Routes>
        </Content>
      </Layout>
    </BrowserRouter>
  );
}
