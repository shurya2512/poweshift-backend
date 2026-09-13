'use client';

import React, { useEffect, useRef, useSyncExternalStore } from 'react';
import { gsap } from 'gsap';
import styles from './MagicBento.module.css';

// Effects from React Bits' MagicBento, reworked to wrap existing panels instead of a fixed demo grid,
// and tinted with the site's blue→red brand gradient instead of purple.

const DEFAULT_PARTICLE_COUNT = 12;
const DEFAULT_SPOTLIGHT_RADIUS = 300;
const MOBILE_QUERY = '(max-width: 768px)';

// Site's brand gradient: blue on the left, red on the right.
const BRAND_BLUE = [59, 130, 246];
const BRAND_RED = [239, 68, 68];

/** "r, g, b" at fraction `t` (clamped to 0–1) along the blue→red brand gradient. */
const brandColorAt = (t: number) => {
  const k = Math.min(1, Math.max(0, t));
  return BRAND_BLUE.map((c, i) => Math.round(c + (BRAND_RED[i] - c) * k)).join(', ');
};

/** Glow strength (0–1) at `distance` px from a card: full within half the radius, gone by three quarters. */
const glowAt = (distance: number, radius: number) => {
  const proximity = radius * 0.5;
  const fadeDistance = radius * 0.75;
  if (distance <= proximity) return 1;
  if (distance >= fadeDistance) return 0;
  return (fadeDistance - distance) / (fadeDistance - proximity);
};

/** Distance in px from a point to the nearest edge of `rect` (0 when inside). */
const distanceToRect = (x: number, y: number, rect: DOMRect) =>
  Math.hypot(Math.max(rect.left - x, 0, x - rect.right), Math.max(rect.top - y, 0, y - rect.bottom));

/** Aims a card's border glow at the cursor, coloured by where the cursor sits across the card. Returns the cursor's distance to the card. */
const updateCardGlow = (card: HTMLElement, x: number, y: number, radius: number) => {
  const rect = card.getBoundingClientRect();
  const fx = (x - rect.left) / rect.width;
  const distance = distanceToRect(x, y, rect);
  card.style.setProperty('--glow-x', `${fx * 100}%`);
  card.style.setProperty('--glow-y', `${((y - rect.top) / rect.height) * 100}%`);
  card.style.setProperty('--glow-intensity', `${glowAt(distance, radius)}`);
  card.style.setProperty('--glow-radius', `${radius}px`);
  card.style.setProperty('--glow-color', brandColorAt(fx));
  return distance;
};

const subscribeMobile = (onChange: () => void) => {
  const query = window.matchMedia(MOBILE_QUERY);
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
};

/** True at or below the mobile breakpoint, where the effects are switched off. */
const useIsMobile = () =>
  useSyncExternalStore(subscribeMobile, () => window.matchMedia(MOBILE_QUERY).matches, () => false);

/** Wraps BentoCards and drives the shared cursor spotlight plus each card's border glow. */
export function BentoSection({
  children,
  className = '',
  spotlightRadius = DEFAULT_SPOTLIGHT_RADIUS,
}: {
  children: React.ReactNode;
  className?: string;
  spotlightRadius?: number;
}) {
  const sectionRef = useRef<HTMLDivElement>(null);
  const isMobile = useIsMobile();

  useEffect(() => {
    const section = sectionRef.current;
    if (isMobile || !section) return;

    const spotlight = document.createElement('div');
    spotlight.className = styles.spotlight;
    document.body.appendChild(spotlight);

    const cards = () => [...section.querySelectorAll<HTMLElement>('[data-bento-card]')];

    const hide = () => {
      cards().forEach(card => card.style.setProperty('--glow-intensity', '0'));
      gsap.to(spotlight, { opacity: 0, duration: 0.3, ease: 'power2.out', overwrite: 'auto' });
    };

    const handleMouseMove = (e: MouseEvent) => {
      const rect = section.getBoundingClientRect();
      if (distanceToRect(e.clientX, e.clientY, rect) > 0) {
        hide();
        return;
      }

      const distances = cards().map(card => updateCardGlow(card, e.clientX, e.clientY, spotlightRadius));
      const opacity = glowAt(Math.min(...distances), spotlightRadius) * 0.8;

      spotlight.style.setProperty('--glow-color', brandColorAt((e.clientX - rect.left) / rect.width));
      gsap.to(spotlight, { left: e.clientX, top: e.clientY, duration: 0.1, ease: 'power2.out', overwrite: 'auto' });
      gsap.to(spotlight, { opacity, duration: opacity > 0 ? 0.2 : 0.5, ease: 'power2.out', overwrite: 'auto' });
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseleave', hide);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseleave', hide);
      gsap.killTweensOf(spotlight);
      spotlight.remove();
    };
  }, [isMobile, spotlightRadius]);

  return (
    <div ref={sectionRef} className={className}>
      {children}
    </div>
  );
}

type BentoCardProps = {
  children: React.ReactNode;
  className?: string;
  enableStars?: boolean;
  particleCount?: number;
  enableTilt?: boolean;
  enableMagnetism?: boolean;
};

/** A panel with MagicBento effects: border glow (driven by BentoSection), magnetism, and optional hover particles and tilt. */
export function BentoCard({
  children,
  className = '',
  enableStars = false,
  particleCount = DEFAULT_PARTICLE_COUNT,
  enableTilt = false,
  enableMagnetism = true,
}: BentoCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const layerRef = useRef<HTMLDivElement>(null);
  const isMobile = useIsMobile();

  useEffect(() => {
    const card = cardRef.current;
    const layer = layerRef.current;
    if (isMobile || !card || !layer) return;

    let hovered = false;
    let timeouts: ReturnType<typeof setTimeout>[] = [];
    let particles: HTMLElement[] = [];

    const spawnParticles = () => {
      const { clientWidth: width, clientHeight: height } = layer;
      timeouts = Array.from({ length: particleCount }, (_, i) =>
        setTimeout(() => {
          if (!hovered) return;
          const particle = document.createElement('div');
          particle.className = styles.particle;
          particle.style.left = `${Math.random() * width}px`;
          particle.style.top = `${Math.random() * height}px`;
          layer.appendChild(particle);
          particles.push(particle);

          gsap.fromTo(particle, { scale: 0, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: 'back.out(1.7)' });
          gsap.to(particle, {
            x: (Math.random() - 0.5) * 100,
            y: (Math.random() - 0.5) * 100,
            rotation: Math.random() * 360,
            duration: 2 + Math.random() * 2,
            ease: 'none',
            repeat: -1,
            yoyo: true,
          });
          gsap.to(particle, { opacity: 0.3, duration: 1.5, ease: 'power2.inOut', repeat: -1, yoyo: true });
        }, i * 100)
      );
    };

    const clearParticles = () => {
      timeouts.forEach(id => clearTimeout(id));
      particles.forEach(particle => {
        gsap.killTweensOf(particle);
        gsap.to(particle, { scale: 0, opacity: 0, duration: 0.3, ease: 'back.in(1.7)', onComplete: () => particle.remove() });
      });
      particles = [];
    };

    const handleMouseEnter = () => {
      hovered = true;
      if (enableStars) spawnParticles();
    };

    const handleMouseLeave = () => {
      hovered = false;
      clearParticles();
      if (enableTilt) gsap.to(card, { rotateX: 0, rotateY: 0, duration: 0.3, ease: 'power2.out', overwrite: 'auto' });
      if (enableMagnetism) gsap.to(card, { x: 0, y: 0, duration: 0.3, ease: 'power2.out', overwrite: 'auto' });
    };

    const handleMouseMove = (e: MouseEvent) => {
      const rect = card.getBoundingClientRect();
      // Cursor offset from the card's centre.
      const dx = e.clientX - rect.left - rect.width / 2;
      const dy = e.clientY - rect.top - rect.height / 2;
      if (enableTilt) {
        gsap.to(card, {
          rotateX: (dy / (rect.height / 2)) * -10,
          rotateY: (dx / (rect.width / 2)) * 10,
          duration: 0.1,
          ease: 'power2.out',
          transformPerspective: 1000,
          overwrite: 'auto',
        });
      }
      if (enableMagnetism) gsap.to(card, { x: dx * 0.05, y: dy * 0.05, duration: 0.3, ease: 'power2.out', overwrite: 'auto' });
    };

    card.addEventListener('mouseenter', handleMouseEnter);
    card.addEventListener('mouseleave', handleMouseLeave);
    card.addEventListener('mousemove', handleMouseMove);

    return () => {
      hovered = false;
      card.removeEventListener('mouseenter', handleMouseEnter);
      card.removeEventListener('mouseleave', handleMouseLeave);
      card.removeEventListener('mousemove', handleMouseMove);
      clearParticles();
    };
  }, [isMobile, enableStars, particleCount, enableTilt, enableMagnetism]);

  return (
    <div ref={cardRef} data-bento-card className={`${styles.card} ${className}`}>
      <div ref={layerRef} aria-hidden="true" className={styles.layer} />
      {children}
    </div>
  );
}
