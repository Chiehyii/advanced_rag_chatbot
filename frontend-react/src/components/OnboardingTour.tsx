import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { Language } from '../types';

export interface TourStep {
  /** CSS selector for the target element to highlight */
  targetSelector: string;
  /** Fallback: if target not found, show centered modal instead */
  fallback?: boolean;
  /** i18n key prefix — will look up `${key}_title` and `${key}_desc` */
  i18nKey: string;
  /** Preferred tooltip position relative to target */
  position: 'top' | 'bottom' | 'left' | 'right';
}

interface OnboardingTourProps {
  isOpen: boolean;
  onClose: () => void;
  language: Language;
  steps: TourStep[];
  translations: Record<string, string>;
}

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

const PADDING = 8; // extra px around the spotlight
const TOOLTIP_GAP = 14; // gap between spotlight and tooltip

/** Check if a DOM element is actually visible (not display:none, not zero-size) */
function isElementVisible(el: Element): boolean {
  const htmlEl = el as HTMLElement;
  // offsetParent is null when the element or any ancestor has display:none
  // (except for <body>, position:fixed, etc.)
  if (htmlEl.offsetParent === null && getComputedStyle(htmlEl).position !== 'fixed') {
    return false;
  }
  const rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

export const OnboardingTour: React.FC<OnboardingTourProps> = ({
  isOpen,
  onClose,
  language,
  steps,
  translations: t,
}) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [targetRect, setTargetRect] = useState<Rect | null>(null);
  const [isAnimating, setIsAnimating] = useState(false);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({});
  // Filter steps to only include those whose target element is visible
  const [visibleSteps, setVisibleSteps] = useState<TourStep[]>([]);

  // Compute visible steps when the tour opens or window resizes
  const computeVisibleSteps = useCallback(() => {
    const filtered = steps.filter(step => {
      const el = document.querySelector(step.targetSelector);
      return el && isElementVisible(el);
    });
    setVisibleSteps(filtered);
  }, [steps]);

  useEffect(() => {
    if (isOpen) {
      // Small delay to ensure the mobile menu has finished closing
      const timer = setTimeout(() => {
        computeVisibleSteps();
        setCurrentStep(0);
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [isOpen, computeVisibleSteps]);

  // Re-compute visible steps on window resize
  useEffect(() => {
    if (!isOpen) return;
    const handleResize = () => {
      computeVisibleSteps();
      setCurrentStep(0); // reset to first visible step on resize
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [isOpen, computeVisibleSteps]);

  // Measure target element position
  const measureTarget = useCallback(() => {
    if (!isOpen || visibleSteps.length === 0) return;
    const step = visibleSteps[currentStep];
    if (!step) return;
    const el = document.querySelector(step.targetSelector);
    if (el && isElementVisible(el)) {
      const rect = el.getBoundingClientRect();
      setTargetRect({
        top: rect.top - PADDING,
        left: rect.left - PADDING,
        width: rect.width + PADDING * 2,
        height: rect.height + PADDING * 2,
      });
    } else {
      // Fallback: center of screen
      setTargetRect(null);
    }
  }, [isOpen, currentStep, visibleSteps]);

  useEffect(() => {
    measureTarget();
    // Re-measure on scroll
    window.addEventListener('scroll', measureTarget, true);
    return () => {
      window.removeEventListener('scroll', measureTarget, true);
    };
  }, [measureTarget]);

  // Calculate tooltip position after targetRect changes
  useEffect(() => {
    if (!isOpen) return;
    // Small delay to let the DOM settle
    const raf = requestAnimationFrame(() => {
      if (!tooltipRef.current) return;
      const tooltip = tooltipRef.current;
      const tw = tooltip.offsetWidth;
      const th = tooltip.offsetHeight;
      const vw = window.innerWidth;
      const vh = window.innerHeight;

      if (!targetRect) {
        // Centered fallback
        setTooltipStyle({
          top: `${Math.max(20, (vh - th) / 2)}px`,
          left: `${Math.max(20, (vw - tw) / 2)}px`,
        });
        return;
      }

      const step = visibleSteps[currentStep];
      if (!step) return;
      let top = 0;
      let left = 0;

      switch (step.position) {
        case 'bottom':
          top = targetRect.top + targetRect.height + TOOLTIP_GAP;
          left = targetRect.left + targetRect.width / 2 - tw / 2;
          break;
        case 'top':
          top = targetRect.top - th - TOOLTIP_GAP;
          left = targetRect.left + targetRect.width / 2 - tw / 2;
          break;
        case 'right':
          top = targetRect.top + targetRect.height / 2 - th / 2;
          left = targetRect.left + targetRect.width + TOOLTIP_GAP;
          break;
        case 'left':
          top = targetRect.top + targetRect.height / 2 - th / 2;
          left = targetRect.left - tw - TOOLTIP_GAP;
          break;
      }

      // Clamp within viewport
      top = Math.max(12, Math.min(top, vh - th - 12));
      left = Math.max(12, Math.min(left, vw - tw - 12));

      setTooltipStyle({ top: `${top}px`, left: `${left}px` });
    });
    return () => cancelAnimationFrame(raf);
  }, [targetRect, isOpen, currentStep, visibleSteps]);

  const goToStep = (idx: number) => {
    setIsAnimating(true);
    setTimeout(() => {
      setCurrentStep(idx);
      setIsAnimating(false);
    }, 200);
  };

  const handleNext = () => {
    if (currentStep < visibleSteps.length - 1) {
      goToStep(currentStep + 1);
    } else {
      onClose();
    }
  };

  const handlePrev = () => {
    if (currentStep > 0) {
      goToStep(currentStep - 1);
    }
  };

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowRight') handleNext();
      if (e.key === 'ArrowLeft') handlePrev();
    },
    [isOpen, currentStep, visibleSteps.length]
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  if (!isOpen || visibleSteps.length === 0) return null;

  const step = visibleSteps[currentStep];
  if (!step) return null;
  const title = t[`${step.i18nKey}_title`] || '';
  const desc = t[`${step.i18nKey}_desc`] || '';
  const isLast = currentStep === visibleSteps.length - 1;

  return (
    <div className="tour-overlay-root">
      {/* 4-piece cutout overlay */}
      {targetRect ? (
        <>
          {/* Top */}
          <div
            className="tour-overlay-piece"
            style={{ top: 0, left: 0, right: 0, height: `${targetRect.top}px` }}
          />
          {/* Left */}
          <div
            className="tour-overlay-piece"
            style={{
              top: `${targetRect.top}px`,
              left: 0,
              width: `${targetRect.left}px`,
              height: `${targetRect.height}px`,
            }}
          />
          {/* Right */}
          <div
            className="tour-overlay-piece"
            style={{
              top: `${targetRect.top}px`,
              left: `${targetRect.left + targetRect.width}px`,
              right: 0,
              height: `${targetRect.height}px`,
            }}
          />
          {/* Bottom */}
          <div
            className="tour-overlay-piece"
            style={{
              top: `${targetRect.top + targetRect.height}px`,
              left: 0,
              right: 0,
              bottom: 0,
            }}
          />
          {/* Spotlight ring */}
          <div
            className="tour-spotlight"
            style={{
              top: `${targetRect.top}px`,
              left: `${targetRect.left}px`,
              width: `${targetRect.width}px`,
              height: `${targetRect.height}px`,
            }}
          />
        </>
      ) : (
        /* Full overlay when no target found */
        <div className="tour-overlay-piece" style={{ top: 0, left: 0, right: 0, bottom: 0 }} />
      )}

      {/* Tooltip card */}
      <div
        ref={tooltipRef}
        className={`tour-tooltip ${isAnimating ? 'tour-tooltip-exit' : 'tour-tooltip-enter'}`}
        style={tooltipStyle}
      >
        {/* Close button */}
        <button className="tour-close-btn" onClick={onClose} title="Close">
          <X size={16} strokeWidth={2} />
        </button>

        {/* Step indicator label */}
        <div className="tour-step-label">
          {currentStep + 1} / {visibleSteps.length}
        </div>

        {/* Content */}
        <h3 className="tour-title">{title}</h3>
        <p className="tour-desc">{desc}</p>

        {/* Navigation */}
        <div className="tour-nav">
          <button
            className="tour-nav-btn tour-nav-skip"
            onClick={onClose}
          >
            {language === 'zh' ? '跳過' : 'Skip'}
          </button>

          <div className="tour-dots">
            {visibleSteps.map((_, idx) => (
              <span
                key={idx}
                className={`tour-dot ${idx === currentStep ? 'active' : ''} ${idx < currentStep ? 'done' : ''}`}
                onClick={() => goToStep(idx)}
              />
            ))}
          </div>

          <div className="tour-nav-arrows">
            {currentStep > 0 && (
              <button className="tour-nav-btn tour-nav-prev" onClick={handlePrev}>
                <ChevronLeft size={18} />
              </button>
            )}
            <button className="tour-nav-btn tour-nav-next" onClick={handleNext}>
              {isLast
                ? (language === 'zh' ? '完成' : 'Done')
                : (language === 'zh' ? '下一步' : 'Next')}
              {!isLast && <ChevronRight size={16} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
