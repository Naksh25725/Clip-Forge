import { renderHook, act } from '@testing-library/react';
import { useUpload } from '../use-upload';
import type { Video } from '@/types';

// Mock XHR
const mockXhr = {
  open: jest.fn(),
  send: jest.fn(),
  abort: jest.fn(),
  upload: {
    onprogress: null as any,
  },
  onload: null as any,
  onerror: null as any,
  onabort: null as any,
  status: 0,
  responseText: '',
};

let xhrInstances: typeof mockXhr[] = [];

beforeAll(() => {
  window.XMLHttpRequest = jest.fn().mockImplementation(() => {
    const instance = {
      open: jest.fn(),
      send: jest.fn(),
      abort: jest.fn(),
      upload: {
        onprogress: null,
      },
      onload: null,
      onerror: null,
      onabort: null,
      status: 0,
      responseText: '',
    };
    xhrInstances.push(instance);
    return instance;
  }) as any;
});

beforeEach(() => {
  jest.clearAllMocks();
  xhrInstances = [];
});

describe('useUpload', () => {
  it('should initialize with empty items', () => {
    const { result } = renderHook(() => useUpload());
    expect(result.current.items).toEqual([]);
  });

  it('should add a file and start uploading', () => {
    const { result } = renderHook(() => useUpload());

    const file = new File(['hello'], 'test.mp4', { type: 'video/mp4' });

    act(() => {
      result.current.upload([file]);
    });

    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0].file).toBe(file);
    expect(result.current.items[0].status).toBe('uploading');
    expect(result.current.items[0].progress).toBe(0);

    expect(xhrInstances).toHaveLength(1);
    expect(xhrInstances[0].open).toHaveBeenCalledWith('POST', expect.stringContaining('/api/videos/upload'));
    expect(xhrInstances[0].send).toHaveBeenCalledWith(expect.any(FormData));
  });

  it('should update progress on upload.onprogress', () => {
    const { result } = renderHook(() => useUpload());
    const file = new File(['hello'], 'test.mp4', { type: 'video/mp4' });

    act(() => {
      result.current.upload([file]);
    });

    const xhr = xhrInstances[0];

    act(() => {
      if (xhr.upload.onprogress) {
        xhr.upload.onprogress({ lengthComputable: true, loaded: 50, total: 100 } as any);
      }
    });

    expect(result.current.items[0].progress).toBe(50);
  });

  it('should handle successful upload', () => {
    const onComplete = jest.fn();
    const { result } = renderHook(() => useUpload(onComplete));
    const file = new File(['hello'], 'test.mp4', { type: 'video/mp4' });

    act(() => {
      result.current.upload([file]);
    });

    const xhr = xhrInstances[0];
    xhr.status = 200;
    const mockVideo: Partial<Video> = { id: 'vid-123', name: 'test.mp4' };
    xhr.responseText = JSON.stringify(mockVideo);

    act(() => {
      if (xhr.onload) xhr.onload({} as any);
    });

    expect(result.current.items[0].status).toBe('done');
    expect(result.current.items[0].progress).toBe(100);
    expect(result.current.items[0].video).toEqual(mockVideo);
    expect(onComplete).toHaveBeenCalledWith(mockVideo);
  });

  it('should handle upload error from server', () => {
    const { result } = renderHook(() => useUpload());
    const file = new File(['hello'], 'test.mp4', { type: 'video/mp4' });

    act(() => {
      result.current.upload([file]);
    });

    const xhr = xhrInstances[0];
    xhr.status = 400;
    xhr.responseText = JSON.stringify({ detail: 'File too large' });

    act(() => {
      if (xhr.onload) xhr.onload({} as any);
    });

    expect(result.current.items[0].status).toBe('error');
    expect(result.current.items[0].error).toBe('File too large');
  });

  it('should handle network error', () => {
    const { result } = renderHook(() => useUpload());
    const file = new File(['hello'], 'test.mp4', { type: 'video/mp4' });

    act(() => {
      result.current.upload([file]);
    });

    const xhr = xhrInstances[0];

    act(() => {
      if (xhr.onerror) xhr.onerror({} as any);
    });

    expect(result.current.items[0].status).toBe('error');
    expect(result.current.items[0].error).toBe('Network error');
  });

  it('should cancel an ongoing upload', () => {
    const { result } = renderHook(() => useUpload());
    const file = new File(['hello'], 'test.mp4', { type: 'video/mp4' });

    act(() => {
      result.current.upload([file]);
    });

    const id = result.current.items[0].id;
    const xhr = xhrInstances[0];

    // Implement what the XHR abort function does natively: triggers onabort event
    xhr.abort.mockImplementation(() => {
      if (xhr.onabort) xhr.onabort({} as any);
    });

    act(() => {
      result.current.cancel(id);
    });

    expect(xhr.abort).toHaveBeenCalled();
    expect(result.current.items[0].status).toBe('cancelled');
  });

  it('should clear finished items', () => {
    const { result } = renderHook(() => useUpload());
    const file1 = new File(['1'], '1.mp4', { type: 'video/mp4' });
    const file2 = new File(['2'], '2.mp4', { type: 'video/mp4' });
    const file3 = new File(['3'], '3.mp4', { type: 'video/mp4' });

    act(() => {
      result.current.upload([file1, file2, file3]);
    });

    // Mark 1 as done, 2 as error, 3 as uploading
    const xhr1 = xhrInstances[0];
    xhr1.status = 200;
    xhr1.responseText = '{}';
    act(() => { if (xhr1.onload) xhr1.onload({} as any); });

    const xhr2 = xhrInstances[1];
    xhr2.status = 500;
    xhr2.responseText = '{}';
    act(() => { if (xhr2.onload) xhr2.onload({} as any); });

    // State should now have done, error, uploading
    expect(result.current.items.map(i => i.status)).toEqual(['done', 'error', 'uploading']);

    act(() => {
      result.current.clearFinished();
    });

    // Only 'uploading' should remain
    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0].status).toBe('uploading');
  });
});
