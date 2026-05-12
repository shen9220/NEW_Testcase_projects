import api from './api';
import type { ApiResponse, LogEntry, PaginatedData } from '../types';

export async function getTaskLogs(taskId: string, page = 1, pageSize = 50): Promise<ApiResponse<PaginatedData<LogEntry>>> {
  return api.get('/logs', { params: { task_id: taskId, page, page_size: pageSize } });
}

export async function getAllLogs(page = 1, pageSize = 50, operationType = ''): Promise<ApiResponse<PaginatedData<LogEntry>>> {
  return api.get('/logs/all', { params: { page, page_size: pageSize, operation_type: operationType } });
}

export async function logFrontendAction(
  taskId: string, operationType: string, detail: string,
): Promise<void> {
  api.post('/logs/action', {
    task_id: taskId, operation_type: operationType, detail,
  }).catch(() => {}); // Fire-and-forget
}

export async function clearAllLogs(): Promise<ApiResponse<{ deleted: number }>> {
  return api.delete('/logs/all');
}
