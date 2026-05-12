export function downloadExcel(taskId: string, module: string = '') {
  const a = document.createElement('a');
  const params = new URLSearchParams({ task_id: taskId });
  if (module) params.set('module', module);
  a.href = `/api/v1/export/excel?${params.toString()}`;
  a.download = module ? `testcases_${module}.xlsx` : `testcases_${taskId}.xlsx`;
  a.click();
}

export function downloadXmind(taskId: string, module: string = '') {
  const a = document.createElement('a');
  const params = new URLSearchParams({ task_id: taskId });
  if (module) params.set('module', module);
  a.href = `/api/v1/export/xmind?${params.toString()}`;
  a.download = module ? `testcases_${module}.xmind` : `testcases_${taskId}.xmind`;
  a.click();
}
