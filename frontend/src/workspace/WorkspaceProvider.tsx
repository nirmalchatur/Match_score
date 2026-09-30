import { useMemo } from 'react'
import type { ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import { useApplications, useJobs, useResumes } from '../hooks/useData'
import { useToasts } from '../hooks/useToasts'
import { WorkspaceContext } from './useWorkspace'
import type { WorkspaceContextValue } from './useWorkspace'

/**
 * Owns the workspace's server state for the whole `/app` subtree.
 *
 * Why this is a layout route rather than a hook call inside `AppShell`
 * -------------------------------------------------------------------
 * `AppShell` was rendered separately per path (`/app/dashboard`, `/app/jobs`,
 * ...), so every navigation *unmounted* it and mounted a new one. Each mount
 * refetched the job list, the resumes, the applications and the dashboard
 * aggregates -- and the job list is the largest response the app sends, so
 * moving between two pages redownloaded the entire job library. On a real
 * connection that is the "click and wait, click and wait" the workspace had,
 * with a refresh spinner on every page change.
 *
 * A layout route element stays mounted while its children swap, so the data is
 * fetched once per sign-in instead of once per click. The refresh buttons still
 * go through the same `refresh` functions, so nothing is stale that was not
 * stale before.
 *
 * Not a caching library: React Query and friends would be a dependency and a
 * second way to think about server state for what is four endpoints and an
 * explicit refresh. What they would add -- request de-duplication, background
 * revalidation -- is not what was wrong here.
 */
export function WorkspaceProvider({ children }: { children?: ReactNode }) {
  const {
    jobs,
    loading: jobsLoading,
    error: jobsError,
    refresh: refreshJobs,
  } = useJobs()

  const {
    resumes,
    master,
    loading: resumesLoading,
    error: resumesError,
    refresh: refreshResumes,
  } = useResumes()

  const {
    applications,
    stats,
    loading: applicationsLoading,
    error: applicationsError,
    refresh: refreshApplications,
    create: createApplication,
    setStatus: setApplicationStatus,
    remove: removeApplication,
  } = useApplications()

  const { toasts, dismiss: dismissToast, notify } = useToasts()

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      jobs,
      jobsLoading,
      jobsError,
      refreshJobs,
      resumes,
      master,
      resumesLoading,
      resumesError,
      refreshResumes,
      applications,
      stats,
      applicationsLoading,
      applicationsError,
      refreshApplications,
      createApplication,
      setApplicationStatus,
      removeApplication,
      toasts,
      dismissToast,
      notify,
    }),
    [
      applications,
      applicationsError,
      applicationsLoading,
      createApplication,
      dismissToast,
      jobs,
      jobsError,
      jobsLoading,
      master,
      notify,
      refreshApplications,
      refreshJobs,
      refreshResumes,
      removeApplication,
      resumes,
      resumesError,
      resumesLoading,
      setApplicationStatus,
      stats,
      toasts,
    ],
  )

  return (
    <WorkspaceContext.Provider value={value}>
      {children ?? <Outlet />}
    </WorkspaceContext.Provider>
  )
}
