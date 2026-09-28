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

/**
 * Skill gap, projected server-side from the existing MatchEngine output.
 *
 * `missing` means "not found in the current resume" -- never "you do not know
 * this". The server owns that wording; the UI must not soften or invert it.
 */
export interface SkillGap {
  has_analysis: boolean
  matched: string[]
  partial: string[]
  missing: string[]
  summary: string
}

export interface Job {
  id: number
  skill_gap?: SkillGap
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
  updated_at?: string
  /** Which master this version was tailored from. Null for the master itself. */
  source_resume?: number | null
  /** Which job this version targets. Null for the master itself. */
  source_job?: number | null
  /** Which AI provider produced the original suggestions. */
  ai_provider?: string
  /** Validation verdict at save time: "valid" | "warning" | "rejected". */
  tailoring_summary?: TailoringVerdict | null
  /** Documents can always be rendered from the structured profile. */
  has_documents?: boolean
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

export type ViewKey = 'dashboard' | 'analyze' | 'jobs' | 'resumes' | 'applications' | 'settings'

export type ToastVariant = 'success' | 'error' | 'info'

export interface Toast {
  id: number
  variant: ToastVariant
  title: string
  message?: string
}

/* ---------- Auth ---------- */

export interface UserProfile {
  headline: string
  discipline: string
  target_locations: string
  created_at?: string
  updated_at?: string
}

export interface User {
  id: number
  email: string
  first_name: string
  last_name: string
  date_joined: string
  profile: UserProfile | null
  has_master_resume: boolean
  job_count: number
}

export interface MeResponse {
  user: User | null
  authenticated: boolean
}

export interface AuthResponse {
  user: User
}

/* ---------- AI resume tailoring ---------- */

/**
 * Verdict from the server-side factual validator.
 *
 * `warning` is still returned to the user for review; `rejected` never reaches
 * the browser as a suggestion, because it claimed something the master resume
 * does not support.
 */
export type TailoringVerdict = 'valid' | 'warning' | 'rejected'

export interface TailoringViolation {
  code: string
  severity: 'warning' | 'rejected'
  message: string
  section: string
  entry_id: string
}

export interface TailoringValidation {
  status: TailoringVerdict
  rejected: boolean
  needs_review: boolean
  violations: TailoringViolation[]
}

export interface SummaryChange {
  original: string
  tailored: string
  reason: string
}

export interface EntryChange {
  entry_id: string
  original_bullets: string[]
  tailored_bullets: string[]
  changes: string[]
}

export interface SkillChanges {
  emphasized: string[]
  deemphasized: string[]
  unsupported_requirements: string[]
}

export interface TailoringResult {
  summary: SummaryChange
  experience: EntryChange[]
  projects: EntryChange[]
  skills: SkillChanges
  warnings: string[]
}

/** A source entry as the server read it from the stored master resume. */
export interface SourceEntry {
  id: string
  name?: string
  label?: string
  bullets: string[]
}

export interface SourceResume {
  summary: string
  skills: string[]
  education: string
  certifications: string
  experience: SourceEntry[]
  projects: SourceEntry[]
}

export interface TailoringResponse {
  result: TailoringResult
  validation: TailoringValidation
  /** The originals come from our database, not from the model's echo. */
  source: SourceResume
  provider: { provider?: string; display_name?: string; model?: string | null }
  job: { id: number; title: string; company: string }
  master_resume_id: number
}

export interface TailoringStatus {
  provider: string | null
  available: boolean
  message?: string
  registered?: string[]
  display_name?: string
  /** The configured model, e.g. "llama3.1". Never a URL or a credential. */
  model?: string | null
  /**
   * True when the provider is only usable once this account supplies a key.
   * Set by the server, not the client.
   */
  requires_user_key?: boolean
  /**
   * Whether *this* account has a key saved. Never the key itself -- the
   * backend has no route that can return it.
   */
  user_key_configured?: boolean
  server_key_configured?: boolean
}


/**
 * The candidate's chosen qualities, and everything the picker needs to render.
 *
 * The catalogue and the minimum come from the server on every GET rather than
 * being hard-coded here. That is the point: if the two ever disagreed, the
 * picker would offer options the server rejects, or hide options it accepts.
 * A hard-coded list in the client is a second source of truth that will drift.
 */
export type QualityKind = 'technical' | 'project_management' | 'soft_skills'

export type QualitySelection = Record<QualityKind, string[]>

export interface QualitiesResponse {
  /** The canonical, saved selection. */
  qualities: QualitySelection
  /** How many are selected in total. */
  selected_count: number
  /** Every allowed option, by kind. */
  catalogue: Record<QualityKind, string[]>
  /** Display labels, by kind. */
  labels: Record<QualityKind, string>
  /** Server-enforced minimum across all kinds. */
  minimum_total: number
  /** Kinds in presentation order. */
  kinds: QualityKind[]
}
/**
 * The status of the signed-in user's own provider key.
 *
 * Note what is absent: there is no `api_key` field. The backend deliberately
 * has no endpoint that returns a stored key, so the value cannot be read back
 * even by a caller that would like to.
 */
export interface AiKeyStatus {
  provider: string
  configured: boolean
  /** A 4+4 mask such as "AIza...4f2b", for telling two keys apart. */
  key_hint?: string
  updated_at?: string
}



/* ---------- Application tracker ---------- */

/**
 * The controlled pipeline. Kept in sync with `Application.STATUS_CHOICES` on
 * the server, which is the authority: the API rejects anything not in this set.
 */
export type ApplicationStatus =
  | 'SAVED'
  | 'APPLIED'
  | 'ASSESSMENT'
  | 'INTERVIEW'
  | 'OFFER'
  | 'REJECTED'
  | 'WITHDRAWN'

export const APPLICATION_STATUSES: ApplicationStatus[] = [
  'SAVED',
  'APPLIED',
  'ASSESSMENT',
  'INTERVIEW',
  'OFFER',
  'REJECTED',
  'WITHDRAWN',
]

export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  SAVED: 'Saved',
  APPLIED: 'Applied',
  ASSESSMENT: 'Assessment',
  INTERVIEW: 'Interview',
  OFFER: 'Offer',
  REJECTED: 'Rejected',
  WITHDRAWN: 'Withdrawn',
}

export interface ApplicationJob {
  id: number
  title: string
  company: string
  location: string
  match_score: number | null
  url: string
}

export interface ApplicationResume {
  id: number
  name: string
  resume_type: string
  is_master: boolean
}

export interface Application {
  id: number
  job: number
  tailored_resume: number | null
  status: ApplicationStatus
  applied_at: string | null
  notes: string
  created_at: string
  updated_at: string
  job_detail: ApplicationJob
  resume_detail: ApplicationResume | null
}

export interface ApplicationSummary {
  counts: Record<ApplicationStatus, number>
  total: number
}

export interface DashboardStats {
  jobs: { total: number; scored: number }
  applications: {
    total: number
    by_status: Record<ApplicationStatus, number>
    active: number
    interviews: number
    offers: number
  }
  resumes: { total: number; tailored: number; has_master: boolean }
  match: { average: number | null }
  recent_applications: Array<{
    id: number
    status: ApplicationStatus
    notes: string
    updated_at: string
    tailored_resume_id: number | null
    job: { id: number; title: string; company: string; location: string; match_score: number | null }
  }>
}
