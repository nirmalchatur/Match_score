import { useTheme } from '../hooks/useTheme'
import type { Theme } from '../hooks/useTheme'

/**
 * Three-state switch: light / system / dark.
 *
 * A plain two-icon toggle cannot express "follow my OS", and a user who lands
 * in dark mode by accident has no way back to automatic without picking.
 * Segmented, in the topbar, in the same visual language as the rest of the
 * shell: hairline border, no fill until active.
 */
const OPTIONS: { value: Theme; label: string; hint: string }[] = [
  { value: 'light', label: 'Light', hint: 'Always use the light theme' },
  { value: 'system', label: 'Auto', hint: 'Follow your operating system' },
  { value: 'dark', label: 'Dark', hint: 'Always use the dark theme' },
]

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()

  return (
    <div className="theme-toggle" role="group" aria-label="Colour theme">
      {OPTIONS.map((option) => {
        const active = theme === option.value
        return (
          <button
            key={option.value}
            type="button"
            className={active ? 'theme-opt is-active' : 'theme-opt'}
            aria-pressed={active}
            title={option.hint}
            onClick={() => setTheme(option.value)}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

export default ThemeToggle
