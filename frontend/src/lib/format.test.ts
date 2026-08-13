import { formatDuration, timestamp } from './format';

describe('formatDuration', () => {
  it('handles 0 and negative numbers correctly', () => {
    expect(formatDuration(0)).toBe('0:00');
    expect(formatDuration(-10)).toBe('0:00');
    expect(formatDuration(-3600)).toBe('0:00');
  });

  it('formats seconds correctly', () => {
    expect(formatDuration(5)).toBe('0:05');
    expect(formatDuration(59)).toBe('0:59');
  });

  it('formats minutes and seconds correctly', () => {
    expect(formatDuration(60)).toBe('1:00');
    expect(formatDuration(65)).toBe('1:05');
    expect(formatDuration(3599)).toBe('59:59');
  });

  it('formats hours, minutes, and seconds correctly', () => {
    expect(formatDuration(3600)).toBe('1:00:00');
    expect(formatDuration(3665)).toBe('1:01:05');
    expect(formatDuration(7325)).toBe('2:02:05');
    expect(formatDuration(36000)).toBe('10:00:00');
  });
});

describe('timestamp', () => {
  it('calls formatDuration and behaves the same', () => {
    expect(timestamp(0)).toBe('0:00');
    expect(timestamp(65)).toBe('1:05');
    expect(timestamp(3665)).toBe('1:01:05');
  });
});
