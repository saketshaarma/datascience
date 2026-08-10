export const PageHeader = ({ title, subtitle, actions }) => {
  return (
    <header className="sticky top-0 z-20 h-16 border-b border-[#27272A] bg-[#09090B]/95 backdrop-blur flex items-center justify-between px-8">
      <div>
        <h1 className="font-head font-semibold text-lg text-white leading-none">{title}</h1>
        {subtitle && <p className="text-xs text-zinc-500 mt-1">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-2">{actions}</div>
    </header>
  );
};
