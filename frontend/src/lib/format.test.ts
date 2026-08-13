import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest';
import { formatDate } from './format';

describe('formatDate', () => {
  it('formats a date string correctly', () => {
    // To avoid timezone flakiness, we create a date using local time and get its ISO string
    // This ensures that new Date(isoString).toLocaleDateString() will format it to the expected local day
    const localDate = new Date(2023, 9, 5, 12, 0, 0); // October 5, 2023 at noon local time
    const result = formatDate(localDate.toISOString());

    // We expect the month to be formatted as short text ("Oct")
    expect(result).toMatch(/Oct/i);
    // We expect the year to be numeric ("2023")
    expect(result).toMatch(/2023/);
    // We expect the day to be numeric ("5")
    expect(result).toMatch(/5/);
  });

  it('formats an early year date string correctly', () => {
    // January 1, 2024 at noon local time
    const localDate = new Date(2024, 0, 1, 12, 0, 0);
    const result = formatDate(localDate.toISOString());

    expect(result).toMatch(/Jan/i);
    expect(result).toMatch(/1/);
    expect(result).toMatch(/2024/);
  });

  it('returns "Invalid Date" for invalid date string', () => {
    const result = formatDate('not-a-date');
    expect(result).toBe('Invalid Date');
  });

  it('handles empty string by returning "Invalid Date"', () => {
    const result = formatDate('');
    expect(result).toBe('Invalid Date');
  });
});
