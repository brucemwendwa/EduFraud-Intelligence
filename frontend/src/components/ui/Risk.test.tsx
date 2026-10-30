import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RiskBadge, RiskScoreRing, riskLevelOf } from './Risk';

describe('riskLevelOf', () => {
  it('maps scores to the documented level thresholds', () => {
    expect(riskLevelOf(0)).toBe('low');
    expect(riskLevelOf(29.9)).toBe('low');
    expect(riskLevelOf(30)).toBe('medium');
    expect(riskLevelOf(60)).toBe('high');
    expect(riskLevelOf(80)).toBe('critical');
  });
});

describe('RiskBadge', () => {
  it('shows a text label and score, not colour alone', () => {
    render(<RiskBadge level="critical" score={86.6} />);
    expect(screen.getByText('Critical')).toBeInTheDocument();
    expect(screen.getByText('· 87')).toBeInTheDocument();
  });

  it('renders a neutral state when no assessment exists', () => {
    render(<RiskBadge level={null} />);
    expect(screen.getByText('Not assessed')).toBeInTheDocument();
  });
});

describe('RiskScoreRing', () => {
  it('exposes an accessible description of the score', () => {
    render(<RiskScoreRing score={64} />);
    expect(screen.getByRole('img', { name: 'Risk score 64 of 100, High risk' })).toBeInTheDocument();
  });
});
