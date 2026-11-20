import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

/** Contact address shown on the legal pages. Set VITE_CONTACT_EMAIL in frontend/.env. */
const CONTACT = (import.meta.env.VITE_CONTACT_EMAIL as string | undefined)?.trim() || null
const UPDATED = '19 November 2026'

function LegalPage({ title, intro, children }: { title: string; intro: ReactNode; children: ReactNode }) {
  return (
    <article className="mx-auto max-w-3xl px-4 pt-10 sm:px-6">
      <p className="text-sm font-semibold text-teal">Last updated {UPDATED}</p>
      <h1 className="mt-2 text-4xl font-extrabold tracking-tight">{title}</h1>
      <p className="mt-4 text-lg leading-relaxed text-navy/70">{intro}</p>
      <div className="mt-10 space-y-8 rounded-3xl border border-navy/5 bg-white p-6 shadow-soft sm:p-10 [&_h2]:text-xl [&_h2]:font-bold [&_li]:mt-1.5 [&_p]:mt-3 [&_p]:leading-relaxed [&_p]:text-navy/80 [&_ul]:mt-3 [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5 [&_ul]:text-navy/80">
        {children}
        <section>
          <h2>Contact</h2>
          {CONTACT ? (
            <p>
              Questions about this page? Email{' '}
              <a href={`mailto:${CONTACT}`} className="font-semibold text-teal hover:underline">{CONTACT}</a>.
            </p>
          ) : (
            <p>Questions about this page? Please contact the team that operates this LawBuddy service.</p>
          )}
        </section>
      </div>
    </article>
  )
}

export function Privacy() {
  return (
    <LegalPage
      title="Privacy Policy"
      intro="This page explains what LawBuddy stores about you, why, who else processes it, and how to delete it."
    >
      <section>
        <h2>What we collect</h2>
        <ul>
          <li>
            <strong>Account details:</strong> your email address and (optionally) your name. If you
            use a password, we store only a one-way hash of it, never the password itself.
          </li>
          <li>
            <strong>Google sign-in:</strong> if you sign in with Google, we receive your name, email
            address, profile picture and Google account ID. We do not receive your Google password.
          </li>
          <li>
            <strong>Conversations:</strong> the questions you ask, LawBuddy’s answers, the sources
            cited, and any 👍/👎 ratings you give.
          </li>
          <li>
            <strong>Technical information:</strong> your IP address and request details, used to
            protect the service (for example, limiting repeated failed sign-in attempts).
          </li>
        </ul>
        <p>
          Your sign-in is kept in your browser’s local storage so you stay signed in. LawBuddy does
          not use advertising or tracking cookies.
        </p>
      </section>

      <section>
        <h2>How we use it</h2>
        <ul>
          <li>To answer your questions and keep your conversation history.</li>
          <li>To improve answers, for example by reviewing answers marked as not helpful.</li>
          <li>To keep the service secure and working.</li>
        </ul>
        <p>We do not sell your personal information.</p>
      </section>

      <section>
        <h2>Services that process your data</h2>
        <ul>
          <li>
            <strong>OpenAI</strong> generates answers and search vectors. Your question, recent
            messages from the same conversation, and the relevant legislation text are sent to
            OpenAI for this, under OpenAI’s API terms.
          </li>
          <li><strong>Google</strong> handles sign-in if you choose “Sign in with Google”.</li>
          <li><strong>Neon</strong> hosts the database where accounts and conversations are stored.</li>
        </ul>
        <p>
          Avoid including information you don’t need to, such as other people’s names, ID numbers or
          case numbers. LawBuddy can explain the law without them.
        </p>
      </section>

      <section>
        <h2>How long we keep it</h2>
        <p>
          Your account and conversations are kept until you delete them. Deleting a conversation
          removes its messages and LawBuddy’s memory of it. Deleting your account removes your
          account and all your conversations. Technical logs are kept only as long as needed for
          security and troubleshooting.
        </p>
      </section>

      <section>
        <h2>Your choices</h2>
        <p>
          You can change your name or password and delete your account on your{' '}
          <Link to="/account" className="font-semibold text-teal hover:underline">account page</Link>,
          and delete individual conversations from the chat sidebar.
        </p>
      </section>

      <section>
        <h2>Changes</h2>
        <p>If this policy changes, the date at the top of this page will change too.</p>
      </section>
    </LegalPage>
  )
}

export function Terms() {
  return (
    <LegalPage
      title="Terms of Use"
      intro="By creating an account or using LawBuddy, you agree to these terms. Please read them, especially the section on legal advice."
    >
      <section>
        <h2>LawBuddy is not legal advice</h2>
        <p>
          LawBuddy explains Sri Lankan legislation in general terms, based on the legislation in its
          library. It is not a lawyer and does not give legal advice. Using LawBuddy does not create
          a lawyer–client relationship. For advice about your situation, consult an Attorney-at-Law.
        </p>
      </section>

      <section>
        <h2>Answers can be incomplete or wrong</h2>
        <ul>
          <li>Answers are generated by AI and may contain mistakes or leave things out.</li>
          <li>
            The library may not include every relevant law, the latest amendments, regulations, or
            how courts have interpreted the law.
          </li>
          <li>
            Each answer cites the sections it relies on. Check those sections, and get professional
            advice, before making decisions or taking action.
          </li>
        </ul>
      </section>

      <section>
        <h2>Your account</h2>
        <ul>
          <li>Give accurate information and keep your password secure.</li>
          <li>You are responsible for activity on your account.</li>
          <li>You can delete your account at any time from your account page.</li>
        </ul>
      </section>

      <section>
        <h2>Acceptable use</h2>
        <p>Don’t use LawBuddy to:</p>
        <ul>
          <li>break the law or help others to do so;</li>
          <li>try to break into, overload or disrupt the service, or scrape it automatically;</li>
          <li>share other people’s personal information without need.</li>
        </ul>
        <p>Accounts that break these terms may be suspended or removed.</p>
      </section>

      <section>
        <h2>Availability and liability</h2>
        <p>
          LawBuddy is provided “as is”. It may change, be unavailable or be discontinued. To the
          extent permitted by law, the operators of LawBuddy are not liable for loss arising from
          reliance on its answers.
        </p>
      </section>

      <section>
        <h2>Governing law</h2>
        <p>These terms are governed by the laws of Sri Lanka.</p>
      </section>

      <section>
        <h2>Changes</h2>
        <p>
          We may update these terms. The date at the top shows the latest version; continuing to use
          LawBuddy means you accept it.
        </p>
      </section>
    </LegalPage>
  )
}
