import api from './api';
import type { ApiResponse, TestCase, PaginatedData } from '../types';

export async function listTestcases(
  taskId: string, params?: Record<string, any>
): Promise<ApiResponse<PaginatedData<TestCase>>> {
  return api.get('/testcases', { params: { task_id: taskId, ...params } });
}

export async function getTestcase(taskId: string, caseId: string): Promise<ApiResponse<TestCase>> {
  return api.get(`/testcases/${caseId}`, { params: { task_id: taskId } });
}

export async function updateTestcase(taskId: string, caseId: string, updates: Partial<TestCase>): Promise<ApiResponse<TestCase>> {
  return api.put(`/testcases/${caseId}`, updates, { params: { task_id: taskId } });
}

export async function deleteTestcase(taskId: string, caseId: string): Promise<ApiResponse<any>> {
  return api.delete(`/testcases/${caseId}`, { params: { task_id: taskId } });
}

export async function batchDeleteTestcases(taskId: string, caseIds: string[]): Promise<ApiResponse<any>> {
  return api.post('/testcases/batch-delete', { case_ids: caseIds }, { params: { task_id: taskId } });
}
