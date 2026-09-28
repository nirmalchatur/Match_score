import { Link } from 'react-router-dom'
import { useEffect } from 'react'
import { applySeo } from '../lib/seo'
import { BrandMark, IconArrowRight } from '../components/Icons'

/**
 * 404.
 *
 * This route used to be `<Route path="*" element={<Navigate to="/" replace />} />`,
 * which silently redirected every unknown URL to the homepage. That is worse
 * than showing nothing: a search engine following a bad link sees a 200 with
 * the homepage and records the wrong URL as valid, which is the soft-404
 * pattern. It also means a mistyped path looks like the app decided to send
 * you home, rather than telling you it does not exist.
 */
export function NotFoundPage() {
  useEffect(() => {
    applySeo({
      title: 'Page not found',
      description: 'That page does not exist on TailorUp.',
      path: '/404',
      noindex: true,
    })
  }, [])

  return (
    <div className="mk-landing-shell">
      <div className="notfound">
        <BrandMark size={40} className="notfound-mark" />
        <p className="notfound-code">404</p>
        <h1 className="notfound-title">This page does not exist</h1>
        <p className="notfound-body">
          The link may be out of date, or the address may have a typo in it.
          Everything TailorUp can do starts from your dashboard.
        </p>
        <div className="notfound-actions">
          <Link to="/" className="btn btn-primary btn-lg">
            Go to the homepage
            <IconArrowRight size={16} />
          </Link>
          <Link to="/app/dashboard" className="btn btn-ghost btn-lg">
            Open my dashboard
          </Link>
        </div>
      </div>
    </div>
  )
}

export default NotFoundPage
