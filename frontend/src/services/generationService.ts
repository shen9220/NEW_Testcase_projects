import api from './api';
import type { ApiResponse, GenerationStatus, TestCase, PaginatedData } from '../types';

export async function startGeneration(taskId: string): Promise<ApiResponse<{ task_id: string; status: string }>> {
  return api.post('/generation/start', { task_id: taskId });
}

export async function getGenerationStatus(taskId: string): Promise<ApiResponse<GenerationStatus>> {
  return api.get(`/generation/${taskId}/status`);
}

export async function getGenerationTestcases(
  taskId: string, page = 1, pageSize = 20, module = ''
): Promise<ApiResponse<PaginatedData<TestCase> & { task_id: string }>> {
  return api.get(`/generation/${taskId}/testcases`, { params: { page, page_size: pageSize, module } });
}

export async function getAllTestcases(
  taskId: string
): Promise<ApiResponse<{ task_id: string; items: TestCase[]; total: number }>> {
  return api.get(`/generation/${taskId}/testcases-all`);
}

export async function cancelGeneration(
  taskId: string
): Promise<ApiResponse<{ task_id: string; message: string }>> {
  return api.post(`/generation/${taskId}/cancel`);
}

export async function regenerateSingleModule(
  taskId: string, moduleName: string
): Promise<ApiResponse<{ task_id: string; module: string; message: string }>> {
  return api.post(`/generation/${taskId}/regenerate-module/${encodeURIComponent(moduleName)}`);
}

export async function regenerateUncovered(
  taskId: string
): Promise<ApiResponse<{ task_id: string; status: string; uncovered_modules: string[] }>> {
  return api.post(`/generation/${taskId}/regenerate-modules`);
}
