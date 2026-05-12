import { useMemo, useState } from 'react';
import { Table, Tag, Button, Space, Popconfirm, Collapse, Select, Typography, Tooltip } from 'antd';
import {
  EyeOutlined, EditOutlined, DeleteOutlined, DownloadOutlined,
  CaretRightOutlined,
} from '@ant-design/icons';
import type { TestCase, ModuleGroup } from '../types';
import type { ColumnsType } from 'antd/es/table';

const { Text } = Typography;

const PRIORITY_COLORS: Record<string, string> = { P0: 'red', P1: 'orange', P2: 'blue', P3: 'default' };
const TYPE_COLORS: Record<string, string> = {
  功能测试: 'blue', 异常测试: 'orange', 边界测试: 'purple',
  性能测试: 'cyan', 安全测试: 'red', 兼容性测试: 'green',
};

interface Props {
  testcases: TestCase[];
  selectedRows: string[];
  onSelectChange: (keys: string[]) => void;
  onView: (tc: TestCase) => void;
  onEdit: (tc: TestCase) => void;
  onDelete: (caseId: string) => void;
  onExportModule: (module: string) => void;
  taskId: string;
}

const DEFAULT_MODULES_PER_PAGE = 10;

/** Group test cases by module name */
function groupByModule(testcases: TestCase[]): ModuleGroup[] {
  const map = new Map<string, TestCase[]>();
  for (const tc of testcases) {
    const mod = tc.module || '未分类';
    if (!map.has(mod)) map.set(mod, []);
    map.get(mod)!.push(tc);
  }
  return Array.from(map.entries()).map(([name, cases]) => ({ name, cases }));
}

export default function TestCaseTable({
  testcases, selectedRows, onSelectChange, onView, onEdit, onDelete, onExportModule, taskId,
}: Props) {
  const [expandedModules, setExpandedModules] = useState<string[]>([]);
  const [modulePage, setModulePage] = useState(1);
  const [modulePageSize, setModulePageSize] = useState(DEFAULT_MODULES_PER_PAGE);

  const allModuleGroups = useMemo(() => groupByModule(testcases), [testcases]);

  // Module-level pagination
  const totalModules = allModuleGroups.length;
  const paginatedModuleGroups = useMemo(() => {
    const start = (modulePage - 1) * modulePageSize;
    return allModuleGroups.slice(start, start + modulePageSize);
  }, [allModuleGroups, modulePage, modulePageSize]);

  const columns: ColumnsType<TestCase> = [
    {
      title: '编号',
      dataIndex: 'case_id',
      width: 90,
      ellipsis: true,
    },
    {
      title: '模块',
      dataIndex: 'module',
      width: 110,
      ellipsis: true,
      render: (v: string) => <Tag>{v || '未分类'}</Tag>,
    },
    {
      title: '用例标题',
      dataIndex: 'title',
      width: 260,
      ellipsis: true,
    },
    {
      title: '覆盖状态',
      dataIndex: 'prd_coverage',
      width: 90,
      render: (v: string) => {
        if (v === '未覆盖') return <Tag color="orange">未覆盖</Tag>;
        return <Tag color="green">已覆盖</Tag>;
      },
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 70,
      render: (v: string) => <Tag color={PRIORITY_COLORS[v] || 'default'}>{v}</Tag>,
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 90,
      render: (v: string) => <Tag color={TYPE_COLORS[v] || 'default'}>{v}</Tag>,
    },
    {
      title: '步骤',
      key: 'steps_count',
      width: 55,
      render: (_: any, record: TestCase) => record.steps?.length || 0,
    },
    {
      title: '操作',
      key: 'actions',
      width: 170,
      render: (_: any, record: TestCase) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => onView(record)}>查看</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => onEdit(record)}>编辑</Button>
          <Popconfirm title="确定删除此用例？" onConfirm={() => onDelete(record.case_id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // Render a sub-table for one module's cases
  const renderModuleTable = (cases: TestCase[]) => (
    <Table
      rowKey="case_id"
      columns={columns}
      dataSource={cases}
      size="small"
      pagination={false}
      rowSelection={{
        selectedRowKeys: selectedRows,
        onChange: (keys) => onSelectChange(keys as string[]),
      }}
      scroll={{ x: 1000 }}
    />
  );

  return (
    <div>
      {/* Module-grouped view using Collapse */}
      <Collapse
        activeKey={expandedModules}
        onChange={(keys) => setExpandedModules(keys as string[])}
        expandIcon={({ isActive }) => <CaretRightOutlined rotate={isActive ? 90 : 0} />}
        style={{ marginBottom: 16 }}
      >
        {paginatedModuleGroups.map((group) => (
          <Collapse.Panel
            key={group.name}
            header={
              <Space>
                <Text strong>{group.name}</Text>
                <Tag>{group.cases.length} 条用例</Tag>
                <Tooltip title={`仅下载 ${group.name} 模块用例`}>
                  <Button
                    size="small"
                    icon={<DownloadOutlined />}
                    onClick={(e) => {
                      e.stopPropagation();
                      onExportModule(group.name);
                    }}
                  >
                    下载此模块
                  </Button>
                </Tooltip>
              </Space>
            }
          >
            {renderModuleTable(group.cases)}
          </Collapse.Panel>
        ))}
      </Collapse>

      {/* Module-level pagination controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <Text type="secondary">每页显示：</Text>
          <Select
            size="small"
            value={modulePageSize}
            onChange={(size) => {
              setModulePageSize(size);
              setModulePage(1);
            }}
            options={[
              { value: 5, label: '5 个模块' },
              { value: 10, label: '10 个模块' },
              { value: 20, label: '20 个模块' },
            ]}
            style={{ width: 120 }}
          />
          <Text type="secondary">共 {totalModules} 个模块，{testcases.length} 条用例</Text>
        </Space>
        <Space>
          <Button disabled={modulePage <= 1} onClick={() => setModulePage(modulePage - 1)}>上一页</Button>
          <Text>第 {modulePage} 页</Text>
          <Button disabled={modulePage * modulePageSize >= totalModules} onClick={() => setModulePage(modulePage + 1)}>下一页</Button>
        </Space>
      </div>
    </div>
  );
}
