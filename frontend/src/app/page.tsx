export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col justify-center px-6 py-16 sm:px-12">
      <div className="mb-8 h-1 w-12 rounded-full bg-teal-700" aria-hidden="true" />
      <h1 className="text-5xl font-semibold tracking-tight sm:text-7xl">FlowForge</h1>
      <p className="mt-6 max-w-2xl text-2xl leading-relaxed text-slate-700">
        Business workflows, clearly connected.
      </p>
      <p className="mt-4 max-w-xl text-lg leading-relaxed text-slate-600">
        A shared place to design processes, coordinate approvals, and follow work from start to finish.
      </p>
      <p className="mt-12 text-sm font-medium text-teal-800">In development</p>
    </main>
  );
}
