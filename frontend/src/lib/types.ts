export type JobStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'NEW'
  | 'PROCESSING'
  | 'READY'
  | 'SKIPPED'

export type StepStatus = 'complete' | 'running' | 'pending' | 'failed' | string

export interface PipelineStep {
  name: string
  status: StepStatus
}

export interface Job {
  id: number
  url: string
  company: string
  title: string
  location: string
  description: string
  match_score: number | null
  match_result?: Record<string, unknown> | null
  decision?: string
  status: JobStatus
  error_message?: string
  pipeline_steps?: PipelineStep[]
  created_at?: string
  updated_at?: string
}

export interface Resume {
  id: number
  name: string
  file: string
  resume_type: string
  is_master: boolean
  created_at: string
}

export interface MasterResume {
  resume: Resume | null
  hasMaster: boolean
}

export interface JobQuery {
  q?: string
  status?: string
  sort?: string
}

export interface AnalyzeResponse {
  job_id: number
  status: string
  job: Job
}

export type ViewKey = 'dashboard' | 'analyze' | 'jobs' | 'resumes'

export type ToastVariant = 'success' | 'error' | 'info'

export interface Toast {
  id: number
  variant: ToastVariant
  title: string
  message?: string
}
