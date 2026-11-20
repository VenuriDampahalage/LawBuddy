import goddess from '../../assets/goddess.webp'

const SUGGESTIONS = [
  'Can the police keep me in custody for more than 24 hours?',
  'Is it a crime to access someone’s social media account without permission?',
  'How can I get a copy of a judgment in a criminal case?',
  'What are my fundamental rights if I am arrested?',
]

export default function EmptyState({ name, onPick }: { name: string | null; onPick: (q: string) => void }) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col items-center px-4 pt-10 pb-6 text-center sm:px-6 sm:pt-16">
      <div className="relative w-28">
        <div aria-hidden className="absolute top-[22%] left-1/2 aspect-square w-[95%] -translate-x-1/2 rounded-full bg-teal/15" />
        <img src={goddess} alt="" className="relative w-full" draggable={false} />
      </div>
      <h1 className="mt-4 text-3xl font-extrabold tracking-tight">
        {name ? `Hello, ${name.split(' ')[0]}.` : 'Hello.'} <span className="text-teal">How can I help?</span>
      </h1>
      <p className="mt-2 max-w-lg text-navy/65">
        Describe your situation or ask about a law. I’ll explain it in plain language and show the
        exact sections I used.
      </p>
      <div className="mt-8 grid w-full gap-3 sm:grid-cols-2">
        {SUGGESTIONS.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => onPick(q)}
            className="rounded-2xl border border-navy/10 bg-white p-4 text-left text-sm font-medium shadow-soft transition hover:-translate-y-0.5 hover:border-teal/50"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}
