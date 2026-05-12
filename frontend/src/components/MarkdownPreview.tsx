interface Props {
  content: string;
  maxHeight?: number;
}

export default function MarkdownPreview({ content, maxHeight = 300 }: Props) {
  // Simple markdown rendering — renders basic formatting
  const renderMarkdown = (md: string): string => {
    let html = md
      // Headers
      .replace(/^### (.+)$/gm, '<h4>$1</h4>')
      .replace(/^## (.+)$/gm, '<h3>$1</h3>')
      .replace(/^# (.+)$/gm, '<h2>$1</h2>')
      // Bold
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      // Italic
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      // Inline code
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      // Unordered lists
      .replace(/^- (.+)$/gm, '<li>$1</li>')
      // Line breaks
      .replace(/\n\n/g, '<br/><br/>')
      .replace(/\n/g, '<br/>');

    return html;
  };

  return (
    <div
      className="markdown-preview"
      style={{
        maxHeight,
        overflowY: 'auto',
        padding: '12px 16px',
        background: '#fafafa',
        border: '1px solid #e8e8e8',
        borderRadius: 6,
        lineHeight: 1.7,
        fontSize: 14,
      }}
      dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
    />
  );
}
