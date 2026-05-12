export interface TestStep {
  action: string;
  expected: string;
}

export interface TestCase {
  id: string;
  case_id: string;
  module: string;
  title: string;
  precondition: string;
  steps: TestStep[];
  priority: string;
  type: string;
  tags: string[];
  notes: string;
  prd_coverage?: string; // "已覆盖" or "未覆盖" — whether this case maps to a PRD module
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

export interface Project {
  task_id: string;
  original_filename: string;
  prd_content?: string;
  testcase_count: number;
  status: string;
  created_at: string;
  updated_at?: string;
}

export interface GenerationStats {
  modules_found: number;
  modules_with_warnings?: number;
  warning_details?: Array<{ module: string; reason: string }>;
  modules_covered: number;
  modules_uncovered: string[];
  total_cases: number;
  module_states?: Record<string, {
    status: string; // "covered" | "failed" | "needs_prd_update"
    retries: number;
    reason?: string;
  }>;
}

export interface GenerationStatus {
  task_id: string;
  status: string; // processing / completed / failed / partial
  progress?: {
    current_skill: string;
    skill_index: number;
    total_skills: number;
    skill_name: string;
    detail?: string;
  };
  testcase_count: number;
  stats?: GenerationStats;
  failure?: {
    reason: string;
    details: string[];
    suggestion: string;
  };
  validation_issues?: Array<{
    case_id: string;
    step_index?: number;
    type: string;
    detail: string;
    suggestion: string;
  }>;
  started_at?: string;
  completed_at?: string;
}

export interface ModuleGroup {
  name: string;
  cases: TestCase[];
}

export interface LogEntry {
  id: string;
  task_id: string;
  operation_type: string;
  detail: string;
  operator: string;
  created_at: string;
}

export interface ApiResponse<T = any> {
  code: number;
  data: T;
  message: string;
}

export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
