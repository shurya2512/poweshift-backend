import PathDrawingPortfolioHero from "@/components/ui/path-drawing-portfolio-hero";

export default function DefaultDemo() {
  return (
    <div className="w-full bg-[#0c0a0f] bg-[radial-gradient(ellipse_80%_60%_at_50%_-10%,rgba(240,147,251,0.14),transparent),radial-gradient(ellipse_60%_50%_at_80%_110%,rgba(245,87,108,0.1),transparent)]">
      <PathDrawingPortfolioHero
        className="w-full"
        brand="AORA"
        tagline="UI / Brand Designer — Tokyo"
        eyebrow="Portfolio"
      />
    </div>
  );
}
