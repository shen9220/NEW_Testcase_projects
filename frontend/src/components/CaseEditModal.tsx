import { useState } from 'react';
import { Modal, Form, Input, Select, Button, Space, message } from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import { updateTestcase } from '../services/testcaseService';
import type { TestCase } from '../types';

const { TextArea } = Input;

interface Props {
  testcase: TestCase | null;
  taskId: string;
  onClose: () => void;
  onUpdated: () => void;
}

export default function CaseEditModal({ testcase, taskId, onClose, onUpdated }: Props) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  if (!testcase) return null;

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      await updateTestcase(taskId, testcase.case_id, values);
      message.success('用例已更新');
      onUpdated();
      onClose();
    } catch {
      // Validation or API error
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title={`编辑用例 — ${testcase.case_id}`}
      open={!!testcase}
      onCancel={onClose}
      onOk={handleSave}
      confirmLoading={loading}
      width={700}
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          module: testcase.module,
          title: testcase.title,
          precondition: testcase.precondition,
          priority: testcase.priority,
          type: testcase.type,
          tags: testcase.tags || [],
          notes: testcase.notes,
          steps: testcase.steps?.length ? testcase.steps : [{ action: '', expected: '' }],
        }}
      >
        <Form.Item name="module" label="模块" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="title" label="标题" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="precondition" label="前置条件">
          <TextArea rows={2} />
        </Form.Item>

        <div style={{ display: 'flex', gap: 16 }}>
          <Form.Item name="priority" label="优先级" style={{ flex: 1 }}>
            <Select options={['P0', 'P1', 'P2', 'P3'].map((v) => ({ label: v, value: v }))} />
          </Form.Item>
          <Form.Item name="type" label="类型" style={{ flex: 1 }}>
            <Select options={['功能测试', '异常测试', '边界测试', '性能测试', '安全测试', '兼容性测试'].map((v) => ({ label: v, value: v }))} />
          </Form.Item>
        </div>

        <Form.Item name="tags" label="标签">
          <Select mode="tags" placeholder="输入标签后回车" />
        </Form.Item>

        <Form.List name="steps">
          {(fields, { add, remove }) => (
            <>
              <h4 style={{ marginBottom: 8 }}>测试步骤</h4>
              {fields.map(({ key, name, ...rest }) => (
                <Space key={key} align="baseline" style={{ display: 'flex', marginBottom: 8 }}>
                  <span style={{ width: 24, textAlign: 'center' }}>{name + 1}</span>
                  <Form.Item {...rest} name={[name, 'action']} rules={[{ required: true, message: '请输入操作步骤' }]}>
                    <Input placeholder="操作步骤" style={{ width: 260 }} />
                  </Form.Item>
                  <Form.Item {...rest} name={[name, 'expected']} rules={[{ required: true, message: '请输入预期结果' }]}>
                    <Input placeholder="预期结果" style={{ width: 260 }} />
                  </Form.Item>
                  {fields.length > 1 && (
                    <MinusCircleOutlined onClick={() => remove(name)} style={{ color: '#ff4d4f' }} />
                  )}
                </Space>
              ))}
              <Button type="dashed" onClick={() => add({ action: '', expected: '' })} block icon={<PlusOutlined />}>
                添加步骤
              </Button>
            </>
          )}
        </Form.List>

        <Form.Item name="notes" label="备注">
          <TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
