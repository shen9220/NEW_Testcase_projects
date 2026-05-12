import { useState, useEffect, useCallback } from 'react';
import { Card, Table, Select, Input, Space, Tag, Button, Popconfirm, message } from 'antd';
import { SearchOutlined, DeleteOutlined } from '@ant-design/icons';
import { getAllLogs, clearAllLogs } from '../services/logService';
import type { LogEntry } from '../types';
import dayjs from 'dayjs';

const OPERATION_TYPES = [
  { label: '全部', value: '' },
  { label: '上传', value: 'upload' },
  { label: '生成', value: 'generate' },
  { label: '编辑', value: 'edit' },
  { label: '删除', value: 'delete' },
  { label: '批量删除', value: 'batch_delete' },
  { label: '导出', value: 'export' },
];

const TYPE_COLORS: Record<string, string> = {
  upload: 'blue',
  generate: 'purple',
  edit: 'orange',
  delete: 'red',
  batch_delete: 'red',
  export: 'green',
};

export default function LogCenter() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [opType, setOpType] = useState('');

  const fetchLogs = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const res = await getAllLogs(p, 50, opType);
      setLogs(res.data.items || []);
      setTotal(res.data.total || 0);
    } catch {
      // Handled
    } finally {
      setLoading(false);
    }
  }, [opType]);

  useEffect(() => { fetchLogs(1); }, [fetchLogs]);

  const handleClear = async () => {
    try {
      const res = await clearAllLogs();
      message.success(res.message || '日志已清除');
      fetchLogs(1);
    } catch {
      message.error('清除失败');
    }
  };

  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 180,
      render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '任务ID',
      dataIndex: 'task_id',
      width: 200,
      ellipsis: true,
      render: (v: string) => v || '-',
    },
    {
      title: '操作类型',
      dataIndex: 'operation_type',
      width: 100,
      render: (v: string) => (
        <Tag color={TYPE_COLORS[v] || 'default'}>
          {OPERATION_TYPES.find((t) => t.value === v)?.label || v}
        </Tag>
      ),
    },
    {
      title: '详情',
      dataIndex: 'detail',
      ellipsis: true,
    },
    {
      title: '操作人',
      dataIndex: 'operator',
      width: 80,
    },
  ];

  return (
    <div className="workbench-container">
      <Card
        title="日志中心"
        extra={
          <Space>
            <Select
              style={{ width: 120 }}
              value={opType}
              onChange={(v) => { setOpType(v); setPage(1); }}
              options={OPERATION_TYPES}
            />
            <Button icon={<SearchOutlined />} onClick={() => fetchLogs(1)}>搜索</Button>
            <Popconfirm title="确定清除全部日志？此操作不可恢复" onConfirm={handleClear} okText="确定" cancelText="取消">
              <Button icon={<DeleteOutlined />} danger>清除</Button>
            </Popconfirm>
          </Space>
        }
      >
        <Table
          dataSource={logs}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 50,
            onChange: (p) => { setPage(p); fetchLogs(p); },
            showSizeChanger: false,
            showTotal: (t) => `共 ${t} 条`,
          }}
          size="small"
        />
      </Card>
    </div>
  );
}
