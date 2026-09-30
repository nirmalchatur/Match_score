import { createContext, useContext } from 'react'
import type { Application, ApplicationStatus, DashboardStats, JobSummary, Resume } from '../lib/types'
import type { Toast } from '../lib/types'

/**
 * Workspace data, mounted once for the whole `/app` subtree.
 *
 * Lives in its own module so this file exports no React component, which keeps
 * Fast Refresh working for the provider -- the same reason `useAuth` is split
 * out of `AuthProvider`.
 */
export type WorkspaceContextValue = {
  /** The job list: compact rows, refreshed by the shell's refresh button. */
  jobs: JobSummary[]
  jobsLoading: boolean
  jobsError: string
  refreshJobs: () => void

  resumes: Resume[]
  master: Resume | null
  resumesLoading: boolean
  resumesError: string
  refreshResumes: () => void

  applications: Application[]
  stats: DashboardStats | null
  applicationsLoading: boolean
  applicationsError: string
  refreshApplications: () => void
  createApplication: (jobId: number, tailoredResumeId?: number | null) => Promise<Application>
  setApplicationStatus: (id: number, status: ApplicationStatus) => Promise<Application>
  removeApplication: (id: number) => Promise<void>

  toasts: Toast[]
  dismissToast: (id: number) => void
  notify: {
    success: (title: string, message?: string) => void
    error: (title: string, message?: string) => void
    info: (title: string, message?: string) => void
  }
}

export const WorkspaceContext = createContext<WorkspaceContextValue | null>(null)

export function useWorkspace(): WorkspaceContextValue {
  const context = useContext(WorkspaceContext)
  if (!context) {
    throw new Error('useWorkspace must be used inside a WorkspaceProvider')
  }
  return context
}
