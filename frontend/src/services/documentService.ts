import api from './api';
import type { ApiResponse, Project } from '../types';

export async function uploadDocument(file: File): Promise<ApiResponse<Project>> {
  const formData = new FormData();
  formData.append('file', file);
  return api.post('/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
}

export async function submitRawText(content: string, title: string): Promise<ApiResponse<Project>> {
  return api.post('/documents/raw', { content, title });
}

export async function getDocumentContent(taskId: string): Promise<ApiResponse<Project>> {
  return api.get(`/documents/${taskId}/content`);
}
