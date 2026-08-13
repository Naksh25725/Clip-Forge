import { describe, it, expect } from 'vitest';
import { mediaUrl } from './api';

describe('mediaUrl', () => {
  it('returns empty string if path is falsy', () => {
    expect(mediaUrl('')).toBe('');
    // @ts-expect-error - testing invalid input
    expect(mediaUrl(null)).toBe('');
    // @ts-expect-error - testing invalid input
    expect(mediaUrl(undefined)).toBe('');
  });

  it('returns the original path if it starts with http', () => {
    const url = 'https://example.com/video.mp4';
    expect(mediaUrl(url)).toBe(url);
    const urlHttp = 'http://example.com/video.mp4';
    expect(mediaUrl(urlHttp)).toBe(urlHttp);
  });

  it('prepends API_URL to a relative path', () => {
    // API_URL is defined as `process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"` in api.ts
    // Let's assert against the default fallback or mocked value if we set it.
    // Assuming default if NEXT_PUBLIC_API_URL isn't set in tests.
    expect(mediaUrl('/media/test.mp4')).toBe('http://localhost:8000/media/test.mp4');
  });
});
