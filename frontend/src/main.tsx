import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import './styles/layout.css'
import './styles/components.css'
import './styles/marketing.css'
import './styles/auth.css'
// Imported last, on purpose. This layers the neumorphic treatment over the
// four sheets above by overriding their tokens and component rules, so the
// cascade order is what makes the theme apply. Moving it earlier would let
// those sheets win and silently undo most of it.
import './styles/neumorphism.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
