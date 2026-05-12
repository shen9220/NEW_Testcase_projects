import { Drawer, Descriptions, List, Tag, Empty } from 'antd';
import type { TestCase } from '../types';

const PRIORITY_COLORS: Record<string, string> = { P0: 'red', P1: 'orange', P2: 'blue', P3: 'default' };

interface Props {
  testcase: TestCase | null;
  onClose: () => void;
}

export default function CaseDetailDrawer({ testcase, onClose }: Props) {
  if (!testcase) return null;

  return (
    <Drawer
      title={`用例详情 — ${testcase.case_id}`}
      open={!!testcase}
      onClose={onClose}
      width={560}
    >
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="模块">{testcase.module}</Descriptions.Item>
        <Descriptions.Item label="标题">{testcase.title}</Descriptions.Item>
        <Descriptions.Item label="优先级">
          <Tag color={PRIORITY_COLORS[testcase.priority]}>{testcase.priority}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="类型">{testcase.type}</Descriptions.Item>
        <Descriptions.Item label="标签">
          {testcase.tags?.length ? testcase.tags.map((t) => <Tag key={t}>{t}</Tag>) : '无'}
        </Descriptions.Item>
        <Descriptions.Item label="前置条件">{testcase.precondition || '无'}</Descriptions.Item>
      </Descriptions>

      <h4 style={{ marginTop: 16, marginBottom: 8 }}>测试步骤</h4>
      {testcase.steps?.length ? (
        <List
          size="small"
          bordered
          dataSource={testcase.steps}
          renderItem={(step, idx) => (
            <List.Item>
              <div style={{ width: '100%' }}>
                <div style={{ color: '#1677ff', marginBottom: 4 }}>
                  <strong>步骤 {idx + 1}：</strong>{step.action}
                </div>
                <div style={{ color: '#52c41a' }}>
                  <strong>预期：</strong>{step.expected}
                </div>
              </div>
            </List.Item>
          )}
        />
      ) : (
        <Empty description="无步骤" />
      )}

      {testcase.notes && (
        <div style={{ marginTop: 16, padding: 12, background: '#fffbe6', borderRadius: 6 }}>
          <strong>备注：</strong>{testcase.notes}
        </div>
      )}
    </Drawer>
  );
}
