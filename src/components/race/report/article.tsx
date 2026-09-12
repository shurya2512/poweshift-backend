import React from 'react';

/**
 * Typographic parts of the report article.
 *
 * The race views are a dashboard: dense panels read in any order. This is a document,
 * read top to bottom — so nothing here draws a card. Structure comes from hairline
 * rules, measure and vertical rhythm instead.
 */

/** The reading column. Figures break out of it; prose never does. */
export const Column = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <div className={`mx-auto w-full max-w-[780px] ${className}`}>{children}</div>
);

export const P = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <p className={`text-[15px] leading-[1.85] text-white/60 ${className}`}>{children}</p>
);

/** Opening paragraph. The drop cap marks where the document starts. */
export const Lede = ({ children }: { children: React.ReactNode }) => (
  <p className="text-[19px] leading-[1.7] text-white/80 first-letter:float-left first-letter:mr-3 first-letter:mt-1 first-letter:text-[64px] first-letter:font-black first-letter:leading-[0.78] first-letter:text-white">
    {children}
  </p>
);

export const Section = ({
  index,
  title,
  standfirst,
  children,
}: {
  index: string;
  title: string;
  standfirst?: string;
  children: React.ReactNode;
}) => (
  <section className="mt-28 first:mt-0">
    <div className="border-t border-white/15 pt-6">
      <span className="font-mono text-[11px] tracking-[0.35em] text-sky-400/70">{index}</span>
      <h2 className="mt-3 text-3xl font-black uppercase tracking-tighter text-white md:text-4xl">{title}</h2>
      {standfirst && <p className="mt-3 max-w-[58ch] text-[15px] leading-relaxed text-white/40">{standfirst}</p>}
    </div>
    <div className="mt-10 flex flex-col gap-7">{children}</div>
  </section>
);

/**
 * Detail that would crowd the page but should not be thrown away. Closed by default,
 * so the section carries the figures that matter and keeps the rest one click away.
 */
export const Disclosure = ({ summary, children }: { summary: string; children: React.ReactNode }) => (
  <details className="group border-t border-white/[0.07] pt-4">
    <summary className="flex cursor-pointer list-none items-center gap-2 text-[11px] uppercase tracking-[0.15em] text-white/35 transition-colors hover:text-white/70">
      <span className="text-white/25 transition-transform group-open:rotate-90">›</span>
      {summary}
    </summary>
    <div className="mt-6 flex flex-col gap-6">{children}</div>
  </details>
);

export const Subhead = ({ children }: { children: React.ReactNode }) => (
  <h3 className="mt-4 text-[13px] font-bold uppercase tracking-[0.2em] text-white/70">{children}</h3>
);

/** A quiet aside for a qualification the reader must not skip. */
export const Aside = ({ children }: { children: React.ReactNode }) => (
  <p className="border-l-2 border-white/15 pl-5 text-[14px] leading-[1.8] text-white/45">{children}</p>
);

/** The finding, set large. Used once per section at most. */
export const PullQuote = ({ children }: { children: React.ReactNode }) => (
  <blockquote className="border-y border-white/10 py-7 text-[22px] font-semibold leading-[1.45] tracking-tight text-white/85 md:text-[26px]">
    {children}
  </blockquote>
);

/** Label and value on one ruled line. Replaces the dashboard's stat cards. */
export const DataList = ({ children }: { children: React.ReactNode }) => (
  <dl className="border-t border-white/10">{children}</dl>
);

export const Datum = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="flex items-baseline justify-between gap-8 border-b border-white/[0.06] py-3">
    <dt className="shrink-0 text-[11px] uppercase tracking-[0.15em] text-white/35">{label}</dt>
    <dd className="text-right text-[14px] font-medium text-white/80">{children}</dd>
  </div>
);

/**
 * Wider than the prose column, so a table is not squeezed to the measure of a
 * sentence. Captioned above, numbered, the way a figure in a paper is.
 */
export const Figure = ({
  label,
  title,
  note,
  children,
}: {
  label: string;
  title: string;
  note?: string;
  children: React.ReactNode;
}) => (
  <figure className="my-4 lg:-mx-24">
    <figcaption className="mb-4 lg:px-24">
      <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/30">{label}</span>
      <p className="mt-1.5 text-[13px] font-bold uppercase tracking-[0.15em] text-white/70">{title}</p>
      {note && <p className="mt-1.5 max-w-[62ch] text-[12px] leading-relaxed text-white/35">{note}</p>}
    </figcaption>
    <div className="overflow-x-auto lg:px-24">{children}</div>
  </figure>
);

/** Editorial table: hairlines only, no fill, tabular figures. */
export const Table = ({ children, minWidth = 560 }: { children: React.ReactNode; minWidth?: number }) => (
  <table className="w-full border-collapse text-left tabular-nums" style={{ minWidth }}>
    {children}
  </table>
);

export const Th = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <th
    className={`border-b border-white/20 pb-2 pr-4 text-[10px] font-medium uppercase tracking-[0.15em] text-white/35 ${className}`}
  >
    {children}
  </th>
);

export const Td = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <td className={`border-b border-white/[0.06] py-3 pr-4 text-[13px] text-white/65 ${className}`}>{children}</td>
);

/** The two races keep the same colour everywhere in the document. */
const RECORDED = 'text-sky-300';
const OURS = 'text-emerald-300';

export const Side = ({ side, children }: { side: 'baseline' | 'alternative' | 'shared'; children: React.ReactNode }) => (
  <span
    className={
      side === 'baseline' ? RECORDED : side === 'alternative' ? OURS : 'text-white/40'
    }
  >
    {children}
  </span>
);
