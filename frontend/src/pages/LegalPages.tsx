import { useEffect } from 'react'
import { applySeo } from '../lib/seo'

/**
 * Real contact details, defined once.
 *
 * These appear on the landing page, in the legal pages and in the footer. A
 * single source means changing the address is one edit rather than a search
 * across three files that can drift apart.
 */
export const CONTACT_EMAIL = 'nirmalch1004@gmail.com'
export const LINKEDIN_URL = 'https://www.linkedin.com/in/nirmal-chaturvedi-0931b2257/'
export const GITHUB_URL = 'https://github.com/nirmalchatur/Match_score'

export function LegalShell({
  title,
  path,
  updated,
  children,
}: {
  title: string
  path: string
  updated: string
  children: React.ReactNode
}) {
  useEffect(() => {
    applySeo({ title, description: `TailorUp — ${title}.`, path })
  }, [title, path])

  return (
    <div className="mk-landing-shell">
      <article className="legal">
        <p className="legal-eyebrow">Last updated {updated}</p>
        <h1 className="legal-title">{title}</h1>
        {children}
        <footer className="legal-foot">
          <p>
            Questions? <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> ·{' '}
            <a href={GITHUB_URL} target="_blank" rel="noreferrer">
              Source on GitHub
            </a>
          </p>
        </footer>
      </article>
    </div>
  )
}

/**
 * Privacy Policy.
 *
 * Written from what the code actually does, cross-checked against
 * `docs/SECURITY.md` and `config/settings.py`. Every claim here is something a
 * reader can verify in the repository. Where behaviour depends on a choice the
 * user makes, the policy says so rather than claiming a guarantee that does not
 * hold in every configuration.
 */
export function PrivacyPage() {
  return (
    <LegalShell title="Privacy Policy" path="/privacy" updated="28 September 2026">
      <h2>What TailorUp stores</h2>
      <p>
        Only what the service needs: your account (email and a hashed password),
        your master resume and the tailored versions generated from it, the job
        postings you analyse, your application tracker entries, and your profile
        answers. Your password is hashed and is never stored or logged in
        readable form.
      </p>

      <h2>What leaves your machine</h2>
      <p>
        This depends entirely on which AI provider you choose, and the app
        always shows which one is active.
      </p>
      <ul>
        <li>
          <strong>Ollama (the default).</strong> The model runs on your own
          hardware. Your resume text is not sent to a third party to be scored.
        </li>
        <li>
          <strong>Gemini, if you choose it.</strong> You paste your own Google
          AI Studio key and resume text is sent to Google to perform the
          tailoring. That is a deliberate choice you make, and it is the only
          path on which resume content leaves your machine.
        </li>
      </ul>

      <h2>Your API keys</h2>
      <p>
        A stored third-party key is encrypted at rest before it is saved. It is
        never returned by the API, never written to a log, and never shipped
        inside the browser bundle. Signing out removes it from the server.
      </p>

      <h2>Cookies</h2>
      <p>
        TailorUp sets one session cookie and one CSRF cookie. Both are strictly
        necessary to keep you signed in and to protect you from cross-site
        request forgery, so neither is optional. No advertising or cross-site
        tracking cookies are set.
      </p>

      <h2>Analytics</h2>
      <p>
        Analytics are <strong>off by default</strong>. When enabled, TailorUp
        uses a cookieless provider that records page views in aggregate and sets
        no identifier, no advertising cookie and no cross-site tracking. If a
        cookie banner appears, it is because analytics have been turned on.
      </p>

      <h2>Data isolation</h2>
      <p>
        Your data is scoped to your account at the query level. A request for
        another account's resume, job or application returns <code>404</code>,
        not <code>403</code> — the API never confirms that an id it refuses
        belongs to someone else.
      </p>

      <h2>Retention and deletion</h2>
      <p>
        Data is retained for as long as your account exists. Deleting a resume
        or application removes it. To delete your account and everything in it,
        email <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </p>

      <h2>Contact</h2>
      <p>
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> ·{' '}
        <a href={LINKEDIN_URL} target="_blank" rel="noreferrer">
          LinkedIn
        </a>
      </p>
    </LegalShell>
  )
}

/**
 * Terms & Conditions.
 *
 * Deliberately plain and short. The clause that matters most is the accuracy
 * one: TailorUp assists with writing, it does not decide what is true about
 * you, and submitting generated content as your own is your responsibility.
 */
export function TermsPage() {
  return (
    <LegalShell title="Terms & Conditions" path="/terms" updated="28 September 2026">
      <h2>What TailorUp is</h2>
      <p>
        Free, open-source software. It analyses job postings, scores your
        resume against them, and helps you tailor your resume using a language
        model you choose.
      </p>

      <h2>Your content stays yours</h2>
      <p>
        You keep every right to the resumes, job data and notes you put in. We
        claim no licence over your content beyond the permission needed to store
        it and process it to provide the service.
      </p>

      <h2>Accuracy, and your responsibility</h2>
      <p>
        TailorUp validates its output against your original resume and refuses
        results that invent experience. That is a safeguard, not a guarantee.
        You are responsible for reviewing anything before sending it, and for
        the accuracy of what you submit to an employer. Tailoring text must
        never be used to claim experience you do not have.
      </p>

      <h2>Not professional advice</h2>
      <p>
        Nothing here is legal, career or hiring advice. A match score is a
        comparison against one posting's stated requirements, not an assessment
        of your worth or your chances.
      </p>

      <h2>Acceptable use</h2>
      <ul>
        <li>Do not use TailorUp to submit applications automatically to employers.</li>
        <li>Do not attempt to access another account's data.</li>
        <li>Do not abuse the rate limits or degrade the service for others.</li>
      </ul>

      <h2>No warranty</h2>
      <p>
        Provided "as is", without warranty of any kind, as set out in the MIT
        Licence. It is community-maintained software; check which release you
        are running.
      </p>

      <h2>Changes</h2>
      <p>
        These terms may change as the project does. The date at the top of this
        page is the current version, and the Git history records every change.
      </p>

      <h2>Contact</h2>
      <p>
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> ·{' '}
        <a href={LINKEDIN_URL} target="_blank" rel="noreferrer">
          LinkedIn
        </a>
      </p>
    </LegalShell>
  )
}
