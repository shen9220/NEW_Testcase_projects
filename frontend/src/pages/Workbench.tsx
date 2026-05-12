import { useState, useCallback, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Card, Button, Space, message, Steps, Progress, Tag, Row, Col, Alert, Badge, Typography,
} from 'antd';
import {
  CloudUploadOutlined, ExportOutlined, DeleteOutlined, ReloadOutlined,
  CheckCircleOutlined, WarningOutlined, StopOutlined, SyncOutlined,
} from '@ant-design/icons';
import FileUpload from '../components/FileUpload';
import MarkdownEditor from '../components/MarkdownEditor';
import MarkdownPreview from '../components/MarkdownPreview';
import TestCaseTable from '../components/TestCaseTable';
import CaseDetailDrawer from '../components/CaseDetailDrawer';
import CaseEditModal from '../components/CaseEditModal';
import { uploadDocument, submitRawText } from '../services/documentService';
import {
  startGeneration, getGenerationStatus, getGenerationTestcases, getAllTestcases,
  regenerateUncovered, cancelGeneration, regenerateSingleModule,
} from '../services/generationService';
import { deleteTestcase, batchDeleteTestcases } from '../services/testcaseService';
import { downloadExcel, downloadXmind } from '../services/exportService';
import { logFrontendAction, getTaskLogs } from '../services/logService';
import type { TestCase, GenerationStatus, LogEntry } from '../types';

const SKILL_NAMES = [
  '提取功能模块', '逐模块生成用例', '提取字段约束', '补充边界用例',
  '状态转换补充', '步骤具体化', '语义去重', '后处理校验',
];

export default function Workbench() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [currentTaskId, setCurrentTaskId] = useState<string>('');
  const [prdContent, setPrdContent] = useState<string>('');
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [testcases, setTestcases] = useState<TestCase[]>([]);
  const [totalCases, setTotalCases] = useState(0);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genStatus, setGenStatus] = useState<GenerationStatus | null>(null);
  const [selectedRows, setSelectedRows] = useState<string[]>([]);
  const [detailCase, setDetailCase] = useState<TestCase | null>(null);
  const [editCase, setEditCase] = useState<TestCase | null>(null);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [generationLogs, setGenerationLogs] = useState<string[]>([]);
  const [retryingModule, setRetryingModule] = useState<string | null>(null);
  const logPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ─── Upload file ───────────────────────────────────────────
  const handleFileUpload = useCallback(async (file: File) => {
    setLoading(true);
    try {
      const res = await uploadDocument(file);
      const data = res.data;
      setCurrentTaskId(data.task_id);
      setPrdContent(data.prd_content || '');
      setTestcases([]);
      setTotalCases(0);
      setGenStatus(null);
      setPreviewVisible(true);
      message.success(`文件解析成功: ${data.original_filename}`);
      logFrontendAction(data.task_id, 'upload', `上传文件: ${file.name}`);
    } catch {
      // Error handled by interceptor
    } finally {
      setLoading(false);
    }
  }, []);

  // ─── Manual input ──────────────────────────────────────────
  const handleManualSubmit = useCallback(async (content: string, title: string) => {
    setLoading(true);
    try {
      const res = await submitRawText(content, title);
      const data = res.data;
      setCurrentTaskId(data.task_id);
      setPrdContent(content);
      setTestcases([]);
      setTotalCases(0);
      setGenStatus(null);
      setPreviewVisible(true);
      message.success('PRD 已提交');
      logFrontendAction(data.task_id, 'input', '手动输入PRD内容');
    } catch {
      // Handled by interceptor
    } finally {
      setLoading(false);
    }
  }, []);

  // ─── Generate test cases ───────────────────────────────────
  const handleGenerate = useCallback(async () => {
    if (!currentTaskId) {
      message.warning('请先上传或输入 PRD');
      return;
    }
    setGenerating(true);
    setGenStatus({ status: 'processing', task_id: currentTaskId, testcase_count: 0 });
    logFrontendAction(currentTaskId, 'generate', '点击生成测试用例');
    try {
      await startGeneration(currentTaskId);
      setGenerationLogs([]);
      const poll = setInterval(async () => {
        try {
          const res = await getGenerationStatus(currentTaskId);
          const status = res.data;
          setGenStatus(status);
          // Also fetch logs for live display
          fetchGenerationLogs();
          if (status.status === 'completed' || status.status === 'failed' || status.status === 'partial') {
            clearInterval(poll);
            setGenerating(false);
            fetchGenerationLogs(); // final fetch
            if (status.status === 'completed' || status.status === 'partial') {
              const isCancelled = status.failure?.reason === 'cancelled';
              message[isCancelled ? 'info' : 'success'](
                isCancelled ? '生成已取消' : `生成完成：${status.testcase_count} 条用例`
              );
              fetchTestcases(currentTaskId);
            } else if (status.failure) {
              message.error(status.failure.details?.join('; ') || '生成失败');
            }
          }
        } catch {
          clearInterval(poll);
          setGenerating(false);
        }
      }, 2000);
    } catch {
      setGenerating(false);
    }
  }, [currentTaskId]);

  // ─── Cancel generation ─────────────────────────────────────
  const handleCancel = useCallback(async () => {
    if (!currentTaskId) return;
    try {
      await cancelGeneration(currentTaskId);
      message.info('正在取消生成...');
      logFrontendAction(currentTaskId, 'cancel', '取消生成');
    } catch {
      // handled by interceptor
    }
  }, [currentTaskId]);

  // ─── Fetch test cases ──────────────────────────────────────
  const fetchTestcases = useCallback(async (taskId: string) => {
    try {
      const res = await getAllTestcases(taskId);
      setTestcases(res.data.items || []);
      setTotalCases(res.data.total || 0);
    } catch {
      // Handled
    }
  }, []);

  // ─── Load a history task ───────────────────────────────────
  const handleLoadHistory = useCallback(async (taskId: string) => {
    setCurrentTaskId(taskId);
    setTestcases([]);
    setTotalCases(0);
    setGenStatus(null);
    setGenerating(false);
    try {
      const { getDocumentContent } = await import('../services/documentService');
      const res = await getDocumentContent(taskId);
      setPrdContent(res.data.prd_content || '');
      setPreviewVisible(true);
      logFrontendAction(taskId, 'view', '查看历史任务');
      await fetchTestcases(taskId);
      // Also fetch generation status for stats
      try {
        const statusRes = await getGenerationStatus(taskId);
        setGenStatus(statusRes.data);
      } catch { /* ignore */ }
    } catch {
      // ignore
    }
  }, [fetchTestcases]);

  // ─── Regenerate uncovered modules ──────────────────────────
  const handleRegenerateUncovered = useCallback(async () => {
    if (!currentTaskId) return;
    const uncovered = genStatus?.stats?.modules_uncovered;
    if (!uncovered || uncovered.length === 0) {
      message.info('所有模块已覆盖');
      return;
    }
    setGenerating(true);
    setGenStatus(prev => prev ? { ...prev, status: 'processing' } : null);
    logFrontendAction(currentTaskId, 'regenerate', `补全未覆盖模块: ${uncovered.join(', ')}`);
    try {
      await regenerateUncovered(currentTaskId);
      const poll = setInterval(async () => {
        try {
          const res = await getGenerationStatus(currentTaskId);
          const status = res.data;
          setGenStatus(status);
          if (status.status === 'completed' || status.status === 'failed' || status.status === 'partial') {
            clearInterval(poll);
            setGenerating(false);
            message.success(`补全完成：${status.testcase_count} 条用例`);
            fetchTestcases(currentTaskId);
          }
        } catch {
          clearInterval(poll);
          setGenerating(false);
        }
      }, 2000);
    } catch {
      setGenerating(false);
    }
  }, [currentTaskId, genStatus, fetchTestcases]);

  // ─── Retry single module ────────────────────────────────────
  const handleRetryModule = useCallback(async (moduleName: string) => {
    if (!currentTaskId || generating) return;
    setRetryingModule(moduleName);
    logFrontendAction(currentTaskId, 'regenerate', `单模块重试: ${moduleName}`);
    try {
      await regenerateSingleModule(currentTaskId, moduleName);
      message.success(`正在重新生成模块: ${moduleName}`);
      // Poll until done
      const poll = setInterval(async () => {
        try {
          const res = await getGenerationStatus(currentTaskId);
          const status = res.data;
          if (status.status === 'completed' || status.status === 'failed' || status.status === 'partial') {
            clearInterval(poll);
            setRetryingModule(null);
            setGenStatus(status);
            fetchTestcases(currentTaskId);
            message.success(`模块 ${moduleName} 重新生成完成`);
          }
        } catch {
          clearInterval(poll);
          setRetryingModule(null);
        }
      }, 2000);
    } catch {
      setRetryingModule(null);
      message.error(`模块 ${moduleName} 重新生成失败`);
    }
  }, [currentTaskId, generating, fetchTestcases]);

  // ─── Fetch generation logs ──────────────────────────────────
  const fetchGenerationLogs = useCallback(async () => {
    if (!currentTaskId) return;
    try {
      const res = await getTaskLogs(currentTaskId);
      const logs: LogEntry[] = res.data?.items || res.data || [];
      setGenerationLogs(logs.map((l: LogEntry) =>
        `[${l.created_at?.slice(11, 19) || ''}] ${l.detail || l.operation_type}`
      ));
    } catch {
      // ignore
    }
  }, [currentTaskId]);

  // ─── Load task from URL param ──────────────────────────────
  useEffect(() => {
    const taskIdFromUrl = searchParams.get('task_id');
    if (taskIdFromUrl && taskIdFromUrl !== currentTaskId) {
      handleLoadHistory(taskIdFromUrl);
      // Clear the URL param after loading
      setSearchParams({}, { replace: true });
    }
  }, [searchParams]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Delete a test case ────────────────────────────────────
  const handleDelete = useCallback(async (caseId: string) => {
    try {
      await deleteTestcase(currentTaskId, caseId);
      message.success('用例已删除');
      logFrontendAction(currentTaskId, 'delete', `删除用例: ${caseId}`);
      fetchTestcases(currentTaskId);
    } catch {
      // Handled
    }
  }, [currentTaskId, fetchTestcases]);

  // ─── Batch delete ──────────────────────────────────────────
  const handleBatchDelete = useCallback(async () => {
    if (!selectedRows.length) {
      message.warning('请先选择用例');
      return;
    }
    try {
      await batchDeleteTestcases(currentTaskId, selectedRows);
      message.success(`已批量删除 ${selectedRows.length} 条用例`);
      logFrontendAction(currentTaskId, 'batch_delete', `批量删除 ${selectedRows.length} 条用例`);
      setSelectedRows([]);
      fetchTestcases(currentTaskId);
    } catch {
      // Handled
    }
  }, [currentTaskId, selectedRows, fetchTestcases]);

  // ─── Export per module ─────────────────────────────────────
  const handleExportModule = useCallback((module: string) => {
    downloadExcel(currentTaskId, module);
    logFrontendAction(currentTaskId, 'export', `下载模块: ${module}`);
  }, [currentTaskId]);

  // ─── Derived values ────────────────────────────────────────
  const currentSkillIndex = genStatus?.progress?.skill_index ?? 0;
  const stats = genStatus?.stats;
  const coveragePercent = stats
    ? Math.round((stats.modules_covered / Math.max(stats.modules_found, 1)) * 100)
    : 0;
  const uncoveredModules = stats?.modules_uncovered || [];
  const moduleStates = stats?.module_states || {};

  // Modules marked as needs_prd_update (won't be retried — PRD info insufficient)
  const needsPrdUpdateModules = Object.entries(moduleStates)
    .filter(([, s]) => s.status === 'needs_prd_update')
    .map(([name]) => name);

  return (
    <div className="workbench-container">
      {/* ─── TOP SECTION: PRD Input + Preview ──────────────── */}
      <Row gutter={24} style={{ marginBottom: 24 }}>
        {/* LEFT: PRD Input */}
        <Col xs={24} lg={12}>
          <Card title="输入需求模块" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <div style={{ flex: '1 1 280px' }}>
                <FileUpload onUpload={handleFileUpload} disabled={generating} />
              </div>
              <div style={{ flex: '1 1 280px' }}>
                <MarkdownEditor onSubmit={handleManualSubmit} disabled={generating} />
              </div>
            </div>
            <div style={{ textAlign: 'center', marginTop: 16 }}>
              <Space>
                <Button
                  type="primary"
                  size="large"
                  icon={<CloudUploadOutlined />}
                  loading={generating}
                  onClick={handleGenerate}
                  disabled={!currentTaskId}
                >
                  生成测试用例
                </Button>
                {generating && (
                  <Button
                    size="large"
                    danger
                    icon={<StopOutlined />}
                    onClick={handleCancel}
                  >
                    取消生成
                  </Button>
                )}
              </Space>
            </div>
          </Card>

          {/* Generation Failure */}
          {genStatus?.failure && (
            <Card title="生成失败" style={{ marginBottom: 16, borderColor: '#ff4d4f' }}>
              <p><strong>原因：</strong>{genStatus.failure.details?.join('；')}</p>
              {genStatus.failure.suggestion && <p><strong>建议：</strong>{genStatus.failure.suggestion}</p>}
            </Card>
          )}
        </Col>

        {/* RIGHT: PRD Preview */}
        <Col xs={24} lg={12}>
          {previewVisible && prdContent && (
            <Card title="PRD 解析预览" size="small" style={{ marginBottom: 16 }}>
              <MarkdownPreview content={prdContent} maxHeight={400} />
            </Card>
          )}

          {/* Global Context */}
          {prdContent && (genStatus?.status === 'processing' || testcases.length > 0) && (
            <Card title="PRD 全局上下文" size="small" style={{ marginBottom: 16 }}>
              {(() => {
                const contexts: string[] = [];
                const roleMatch = prdContent.match(/(?:角色|用户角色|权限角色)[：:]\s*(.+?)(?:\n|$)/);
                if (roleMatch) contexts.push(`角色：${roleMatch[1].trim()}`);
                const ruleMatch = prdContent.match(/(?:公共规则|通用规则|全局规则)[：:]*\s*\n(.+?)(?=\n#|\n##|\Z)/s);
                if (ruleMatch) contexts.push(`规则：${ruleMatch[1].trim().slice(0, 200)}`);
                const errorMatch = prdContent.match(/(?:异常处理|错误处理|异常场景)[：:]*\s*\n(.+?)(?=\n#|\n##|\Z)/s);
                if (errorMatch) contexts.push(`异常：${errorMatch[1].trim().slice(0, 100)}`);
                return contexts.length > 0
                  ? contexts.map((c, i) => <div key={i} style={{ fontSize: 12, marginBottom: 4 }}>{c}</div>)
                  : <Typography.Text type="secondary">未检测到明确的全局上下文信息</Typography.Text>;
              })()}
            </Card>
          )}
        </Col>
      </Row>

      {/* ─── Generation Progress (full width) ──────────────── */}
      {genStatus?.status === 'processing' && (
        <Card style={{ marginBottom: 16 }}>
          <div style={{ textAlign: 'center', marginBottom: 12 }}>
            <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>
              当前进度 {Math.round((currentSkillIndex / 8) * 100)}%
            </div>
            <Progress
              percent={Math.round((currentSkillIndex / 8) * 100)}
              status="active"
              strokeColor={{ from: '#108ee9', to: '#87d068' }}
            />
          </div>
          <Steps
            current={currentSkillIndex - 1}
            size="small"
            status={currentSkillIndex > 0 ? 'process' : 'wait'}
            items={SKILL_NAMES.map((name, i) => ({
              title: genStatus.progress?.skill_index === i + 1
                ? genStatus.progress?.skill_name || name
                : name,
            }))}
          />
          {genStatus.progress?.detail && (
            <div style={{ marginTop: 8, color: '#888', fontSize: 13, textAlign: 'center' }}>
              {genStatus.progress.detail}
            </div>
          )}
        </Card>
      )}

      {/* ─── Generation Log Panel (full width) ──────────────── */}
      {(generationLogs.length > 0 || genStatus?.status === 'processing') && (
        <Card title="生成日志" size="small" style={{ marginBottom: 16, maxHeight: 200, overflowY: 'auto' }}>
          {generationLogs.length === 0 ? (
            <Typography.Text type="secondary">等待日志...</Typography.Text>
          ) : (
            generationLogs.map((log, i) => (
              <div key={i} style={{ fontSize: 12, color: '#666', marginBottom: 2, fontFamily: 'monospace' }}>
                {log}
              </div>
            ))
          )}
        </Card>
      )}

      {/* ─── BOTTOM SECTION: Test Cases (full width) ───────── */}
      {testcases.length > 0 ? (
        <>
          {/* Coverage Stats + Regenerate Button */}
          {stats && (
            <Card size="small" style={{ marginBottom: 16 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Space>
                    <strong>模块覆盖率</strong>
                    <Progress
                      percent={coveragePercent}
                      size="small"
                      status={coveragePercent === 100 ? 'success' : 'active'}
                      style={{ width: 160 }}
                    />
                    <span>
                      {stats.modules_covered}/{stats.modules_found} 个模块
                    </span>
                    {coveragePercent === 100 ? (
                      <Tag icon={<CheckCircleOutlined />} color="success">全覆盖</Tag>
                    ) : (
                      <Tag icon={<WarningOutlined />} color="warning">有遗漏</Tag>
                    )}
                  </Space>
                </div>
                {uncoveredModules.length > 0 && (
                  <>
                    <Alert
                      type="warning"
                      showIcon
                      message={
                        <div>
                          <div style={{ marginBottom: 4 }}>未覆盖模块（可单独重试）：</div>
                          {uncoveredModules.filter(m => !needsPrdUpdateModules.includes(m)).map(m => (
                            <Tag key={m} color="orange" style={{ marginRight: 4, marginBottom: 4 }}>
                              {m}
                              <Button
                                size="small"
                                type="link"
                                icon={<SyncOutlined spin={retryingModule === m} />}
                                loading={retryingModule === m}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRetryModule(m);
                                }}
                                style={{ padding: 0, marginLeft: 4, fontSize: 12 }}
                              >
                                重试
                              </Button>
                            </Tag>
                          ))}
                          {uncoveredModules.filter(m => !needsPrdUpdateModules.includes(m)).length === 0 &&
                            <span style={{ color: '#888' }}>无（可重试模块已全部处理）</span>
                          }
                        </div>
                      }
                      action={
                        uncoveredModules.filter(m => !needsPrdUpdateModules.includes(m)).length > 1 && (
                          <Button
                            size="small"
                            type="primary"
                            icon={<ReloadOutlined />}
                            loading={generating}
                            onClick={handleRegenerateUncovered}
                          >
                            全部补全
                          </Button>
                        )
                      }
                    />
                    {needsPrdUpdateModules.length > 0 && (
                      <Alert
                        type="error"
                        showIcon
                        icon={<WarningOutlined />}
                        message={
                          <span>
                            需求缺失模块（PRD信息不足，无法生成测试用例）：
                            {needsPrdUpdateModules.map(m => (
                              <Tag key={m} color="red" style={{ marginRight: 4 }}>{m}</Tag>
                            ))}
                          </span>
                        }
                        description="请补充PRD中对应模块的详细描述（UI元素、操作步骤、业务规则）后重新提交生成。"
                        style={{ marginTop: 8 }}
                      />
                    )}
                  </>
                )}
              </Space>
            </Card>
          )}

          {/* Test Case Table Card */}
          <Card
            title={
              <Space>
                <span>生成的测试用例</span>
                <Badge count={totalCases} overflowCount={9999} style={{ backgroundColor: '#1677ff' }} />
              </Space>
            }
            extra={
              <Space>
                <Button icon={<ExportOutlined />} onClick={() => { downloadExcel(currentTaskId); logFrontendAction(currentTaskId, 'export', '导出全部Excel'); }}>
                  Excel
                </Button>
                <Button icon={<ExportOutlined />} onClick={() => { downloadXmind(currentTaskId); logFrontendAction(currentTaskId, 'export', '导出全部XMind'); }}>
                  XMind
                </Button>
                <Button danger icon={<DeleteOutlined />} onClick={handleBatchDelete}
                        disabled={!selectedRows.length}>
                  批量删除{selectedRows.length > 0 ? ` (${selectedRows.length})` : ''}
                </Button>
              </Space>
            }
          >
            <TestCaseTable
              testcases={testcases}
              selectedRows={selectedRows}
              onSelectChange={setSelectedRows}
              onView={(tc) => {
                setDetailCase(tc);
                logFrontendAction(currentTaskId, 'view', `查看用例: ${tc.case_id}`);
              }}
              onEdit={(tc) => {
                setEditCase(tc);
                logFrontendAction(currentTaskId, 'edit', `编辑用例: ${tc.case_id}`);
              }}
              onDelete={handleDelete}
              onExportModule={handleExportModule}
              taskId={currentTaskId}
            />
          </Card>
        </>
      ) : (
        /* Empty state when no test cases yet */
        (genStatus?.status === 'completed' || genStatus?.status === 'partial') && (
          <Card style={{ marginBottom: 16 }}>
            <Alert message="暂无测试用例" type="info" showIcon />
          </Card>
        )
      )}

      {/* Detail Drawer */}
      <CaseDetailDrawer testcase={detailCase} onClose={() => setDetailCase(null)} />

      {/* Edit Modal */}
      <CaseEditModal
        testcase={editCase}
        taskId={currentTaskId}
        onClose={() => setEditCase(null)}
        onUpdated={() => fetchTestcases(currentTaskId)}
      />
    </div>
  );
}
