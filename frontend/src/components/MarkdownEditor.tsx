import { useState } from 'react';
import { Input, Button, message } from 'antd';
import { SendOutlined } from '@ant-design/icons';

const { TextArea } = Input;

interface Props {
  onSubmit: (content: string, title: string) => void;
  disabled?: boolean;
}

export default function MarkdownEditor({ onSubmit, disabled }: Props) {
  const [content, setContent] = useState('');
  const [title, setTitle] = useState('');

  const handleSubmit = () => {
    if (!content.trim()) {
      message.warning('请输入 PRD 内容');
      return;
    }
    onSubmit(content.trim(), title.trim() || '手动输入');
    setContent('');
    setTitle('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div>
      <Input
        placeholder="模块名称（可选）"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        style={{ marginBottom: 8 }}
        disabled={disabled}
      />
      <TextArea
        rows={4}
        placeholder="在此粘贴或输入 PRD Markdown 内容...&#10;&#10;Ctrl+Enter 快捷提交"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
      />
      <Button
        type="dashed"
        icon={<SendOutlined />}
        onClick={handleSubmit}
        disabled={disabled || !content.trim()}
        style={{ marginTop: 8, width: '100%' }}
      >
        提交 PRD
      </Button>
    </div>
  );
}
