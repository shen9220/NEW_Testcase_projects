import api from './api';
import type { ApiResponse, Project, PaginatedData } from '../types';

export async function listProjects(
  page = 1, pageSize = 20, search = '', status = ''
): Promise<ApiResponse<PaginatedData<Project>>> {
  return api.get('/projects', { params: { page, page_size: pageSize, search, status } });
}

export async function deleteProject(taskId: string): Promise<ApiResponse<{ task_id: string }>> {
  return api.delete(`/projects/${taskId}`);
}
