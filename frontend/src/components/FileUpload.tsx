import { Upload, message } from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import type { UploadProps } from 'antd';

const { Dragger } = Upload;

interface Props {
  onUpload: (file: File) => void;
  disabled?: boolean;
}

export default function FileUpload({ onUpload, disabled }: Props) {
  const props: UploadProps = {
    name: 'file',
    multiple: false,
    accept: '.md,.docx,.pdf',
    showUploadList: false,
    beforeUpload: (file) => {
      const isValid = ['.md', '.docx', '.pdf'].some((ext) =>
        file.name.toLowerCase().endsWith(ext)
      );
      if (!isValid) {
        message.error('仅支持 .md / .docx / .pdf 格式');
        return Upload.LIST_IGNORE;
      }
      if (file.size > 50 * 1024 * 1024) {
        message.error('文件大小不能超过 50MB');
        return Upload.LIST_IGNORE;
      }
      onUpload(file);
      return false; // Prevent auto upload
    },
  };

  return (
    <Dragger {...props} disabled={disabled}>
      <p className="ant-upload-drag-icon">
        <InboxOutlined />
      </p>
      <p className="ant-upload-text">点击或拖拽 PRD 文件到此区域上传</p>
      <p className="ant-upload-hint">支持 .md / .docx / .pdf 格式，最大 50MB</p>
    </Dragger>
  );
}
