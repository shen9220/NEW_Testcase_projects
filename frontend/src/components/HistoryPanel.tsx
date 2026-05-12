import { useState, useEffect, useCallback } from 'react';
import { Card, List, Tag, Button, Spin, Empty, Input, Select, Space, Popconfirm, message } from 'antd';
import { FolderOpenOutlined, DeleteOutlined, SearchOutlined } from '@ant-design/icons';
import { listProjects, deleteProject } from '../services/projectService';
import type { Project } from '../types';
import dayjs from 'dayjs';

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  completed: { color: 'green', label: '完成' },
  processing: { color: 'blue', label: '处理中' },
  failed: { color: 'red', label: '失败' },
  partial: { color: 'orange', label: '部分完成' },
};

interface Props {
  currentTaskId: string;
  onSelect: (taskId: string) => void;
  onDeleted?: () => void;
}

export default function HistoryPanel({ currentTaskId, onSelect, onDeleted }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchProjects = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listProjects(1, 50, search, statusFilter);
      setProjects(res.data.items || []);
    } catch {
      // Handled
    } finally {
      setLoading(false);
    }
  }, [search, statusFilter]);

  useEffect(() => { fetchProjects(); }, [fetchProjects]);

  const handleDelete = useCallback(async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleting(taskId);
    try {
      await deleteProject(taskId);
      message.success('已删除');
      setProjects(prev => prev.filter(p => p.task_id !== taskId));
      onDeleted?.();
    } catch {
      message.error('删除失败');
    } finally {
      setDeleting(null);
    }
  }, [onDeleted]);

  return (
    <Card
      title="历史任务"
      size="small"
      style={{ maxHeight: 'calc(100vh - 100px)', overflowY: 'auto' }}
      extra={
        <Button size="small" icon={<SearchOutlined />} onClick={fetchProjects} loading={loading}>
          刷新
        </Button>
      }
    >
      {/* Search + Filter */}
      <Space direction="vertical" style={{ width: '100%', marginBottom: 8 }} size={4}>
        <Input
          size="small"
          placeholder="搜索文件名或任务ID"
          prefix={<SearchOutlined />}
          value={search}
          onChange={e => setSearch(e.target.value)}
          allowClear
          onPressEnter={() => fetchProjects()}
        />
        <Select
          size="small"
          placeholder="按状态筛选"
          value={statusFilter || undefined}
          onChange={v => setStatusFilter(v || '')}
          allowClear
          style={{ width: '100%' }}
        >
          <Select.Option value="completed">完成</Select.Option>
          <Select.Option value="partial">部分完成</Select.Option>
          <Select.Option value="failed">失败</Select.Option>
          <Select.Option value="processing">处理中</Select.Option>
        </Select>
      </Space>

      {loading ? (
        <Spin />
      ) : projects.length === 0 ? (
        <Empty description="暂无历史任务" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          size="small"
          dataSource={projects}
          renderItem={(item) => {
            const status = STATUS_MAP[item.status] || { color: 'default', label: item.status };
            const isActive = item.task_id === currentTaskId;
            return (
              <List.Item
                style={{ cursor: 'pointer', background: isActive ? '#e6f4ff' : undefined }}
                onClick={() => onSelect(item.task_id)}
                actions={[
                  <Popconfirm
                    key="del"
                    title="确认删除此任务？"
                    description="将同时删除所有关联的测试用例"
                    onConfirm={(e) => handleDelete(item.task_id, e as any)}
                    onCancel={(e) => (e as any)?.stopPropagation()}
                    okText="删除"
                    cancelText="取消"
                  >
                    <Button
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      loading={deleting === item.task_id}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </Popconfirm>,
                  <Button key="open" size="small" icon={<FolderOpenOutlined />} />,
                ]}
              >
                <List.Item.Meta
                  title={
                    <span>
                      <Tag color={status.color} style={{ marginRight: 4 }}>{status.label}</Tag>
                      {item.original_filename || item.task_id}
                    </span>
                  }
                  description={
                    <span>
                      {dayjs(item.created_at).format('MM-DD HH:mm')} · {item.testcase_count} 条用例
                    </span>
                  }
                />
              </List.Item>
            );
          }}
        />
      )}
    </Card>
  );
}
