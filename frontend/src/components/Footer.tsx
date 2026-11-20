import { Link } from 'react-router-dom'

import Logo from './Logo'

const YEAR = new Date().getFullYear()

export default function Footer({ className = '' }: { className?: string }) {
  return (
    <footer className={`bg-navy text-white ${className}`}>
      <div className="mx-auto grid max-w-6xl gap-10 px-6 py-12 md:grid-cols-[1.4fr_1fr_1fr]">
        <div className="max-w-sm">
          <Logo light />
          <p className="mt-3 text-sm leading-relaxed text-white/70">
            Your AI-powered assistant for understanding Sri Lankan law, with references to the
            exact sections it comes from.
          </p>
        </div>

        <nav aria-label="Footer">
          <h2 className="text-sm font-bold">Pages</h2>
          <ul className="mt-3 space-y-2 text-sm text-white/70">
            <li><Link to="/" className="hover:text-teal">Home</Link></li>
            <li><Link to="/chat" className="hover:text-teal">Chat</Link></li>
            <li><Link to="/#features" className="hover:text-teal">Features</Link></li>
            <li><Link to="/#about" className="hover:text-teal">About</Link></li>
          </ul>
        </nav>

        <nav aria-label="Legal">
          <h2 className="text-sm font-bold">Legal</h2>
          <ul className="mt-3 space-y-2 text-sm text-white/70">
            <li><Link to="/privacy" className="hover:text-teal">Privacy Policy</Link></li>
            <li><Link to="/terms" className="hover:text-teal">Terms of Use</Link></li>
          </ul>
        </nav>
      </div>

      <div className="border-t border-white/10">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-6 py-5 text-xs text-white/60 sm:flex-row sm:justify-between">
          <p>LawBuddy provides general legal information, not legal advice.</p>
        </div>
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-6 py-5 text-xs text-white/60 sm:flex-row sm:justify-between">
          <p>© {YEAR} LawBuddy</p>
          <p>Designed & Developed by Kumuditha Venuri Dampahalage</p>
        </div>
      </div>
      
    </footer>
  )
}
