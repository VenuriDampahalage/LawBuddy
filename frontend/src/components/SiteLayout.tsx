import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import authBg from '../assets/auth-bg.webp'
import Footer from './Footer'
import Navbar from './Navbar'

const AUTH_PAGES = new Set(['/login', '/register'])

/** Navbar + page + footer. Most pages get a faint teal wash at the top; the sign-in and
 *  sign-up pages get the full Sri Lankan landscape background behind the card. */
export default function SiteLayout() {
  const { pathname, hash } = useLocation()
  const authPage = AUTH_PAGES.has(pathname)

  // Scroll to "#features" / "#about" anchors, including when arriving from another page.
  useEffect(() => {
    if (hash) {
      document.getElementById(hash.slice(1))?.scrollIntoView()
    } else {
      window.scrollTo(0, 0)
    }
  }, [pathname, hash])

  return (
    <div className="relative min-h-svh overflow-x-clip">
      {/* Navbar + page share one backdrop, so the footer starts right where it ends. */}
      <div className={`relative isolate ${authPage ? 'flex min-h-svh flex-col' : ''}`}>
        {authPage ? (
          <div aria-hidden className="absolute inset-0 -z-10 overflow-hidden bg-white">
            {/* A slight blur hides the illustration's compression artefacts; scaling up
                keeps the blurred edges from fading to white. Phones show the temple on the
                left of the scene; wider screens the whole skyline. */}
            <div
              className="absolute inset-0 scale-105 bg-cover bg-[position:18%_bottom] bg-no-repeat blur-[3px] sm:bg-[position:60%_bottom]"
              style={{ backgroundImage: `url(${authBg})` }}
            />
          </div>
        ) : (
          <div
            aria-hidden
            className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[720px] bg-[radial-gradient(ellipse_at_top,rgb(42_157_143/0.12),transparent_65%)]"
          />
        )}
        <Navbar />
        <main className={authPage ? 'flex flex-1 flex-col' : ''}>
          <Outlet />
        </main>
      </div>
      <Footer className={authPage ? '' : 'mt-24'} />
    </div>
  )
}
