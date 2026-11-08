import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  documentKeys,
  listStaffDocuments,
  listStudentDocuments,
  replaceStudentDocument,
  requestStaffDocumentDownload,
  requestStudentDocumentDownload,
  reviewDocument,
  uploadStudentDocument,
  useReviewDocument,
  useStudentDocumentUpload,
} from './api';

const get = vi.fn();
const post = vi.fn();
const patch = vi.fn();

vi.mock('@/lib/api', async (orig) => ({
  ...(await orig<typeof import('@/lib/api')>()),
  api: {
    get: (...args: unknown[]) => get(...args),
    post: (...args: unknown[]) => post(...args),
    patch: (...args: unknown[]) => patch(...args),
  },
}));

const document = {
  id: 'doc-1', application_id: 'app-1', original_filename: 'income.pdf', detected_mime_type: 'application/pdf',
  size_bytes: 12, category: 'income_evidence', status: 'available', scanner_provider: 'test',
  scanned_at: null, review_status: 'pending', created_at: '2026-01-01T00:00:00Z', reviewed_at: null,
  replaces_document_id: null,
};

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('document API', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    patch.mockReset();
  });

  it('lists student documents for the supplied application', async () => {
    get.mockResolvedValue({ data: [document] });
    await expect(listStudentDocuments('app-1')).resolves.toEqual([document]);
    expect(get).toHaveBeenCalledWith('/student-applications/app-1/documents');
  });

  it('uploads a browser File as the backend multipart fields', async () => {
    post.mockResolvedValue({ data: document });
    const file = new File(['pdf'], 'income.pdf', { type: 'application/pdf' });
    await uploadStudentDocument('app-1', { category: 'income_evidence', file });
    const [path, form] = post.mock.calls[0];
    expect(path).toBe('/student-applications/app-1/documents');
    expect(form).toBeInstanceOf(FormData);
    expect(form.get('category')).toBe('income_evidence');
    expect(form.get('file')).toBe(file);
    expect(post.mock.calls[0]).toHaveLength(2);
  });

  it('sends replacements to the student replacement endpoint', async () => {
    post.mockResolvedValue({ data: document });
    const file = new File(['pdf'], 'replacement.pdf', { type: 'application/pdf' });
    await replaceStudentDocument('doc-1', { category: 'income_evidence', file });
    const [path, form] = post.mock.calls[0];
    expect(path).toBe('/student-documents/doc-1/replace');
    expect(form.get('category')).toBe('income_evidence');
    expect(form.get('file')).toBe(file);
  });

  it('uses the student and staff download endpoints', async () => {
    post.mockResolvedValue({ data: { url: 'https://example.test/document', expires_in_seconds: 60 } });
    await requestStudentDocumentDownload('doc-1');
    await requestStaffDocumentDownload('doc-1');
    expect(post).toHaveBeenNthCalledWith(1, '/student-documents/doc-1/download');
    expect(post).toHaveBeenNthCalledWith(2, '/documents/doc-1/download');
  });

  it('lists staff documents and submits staff reviews', async () => {
    get.mockResolvedValue({ data: [document] });
    patch.mockResolvedValue({ data: document });
    await listStaffDocuments('app-1');
    await reviewDocument('doc-1', { decision: 'accepted', reason: 'Document has been verified.' });
    expect(get).toHaveBeenCalledWith('/applications/app-1/documents');
    expect(patch).toHaveBeenCalledWith('/documents/doc-1/review', {
      decision: 'accepted', reason: 'Document has been verified.',
    });
  });

  it('keeps student and staff query keys distinct', () => {
    expect(documentKeys.student('app-1')).toEqual(['documents', 'student', 'app-1']);
    expect(documentKeys.staff('app-1')).toEqual(['documents', 'staff', 'app-1']);
  });

  it('invalidates both views after a student upload', async () => {
    post.mockResolvedValue({ data: document });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useStudentDocumentUpload(), { wrapper: wrapper(client) });
    result.current.mutate({ applicationId: 'app-1', category: 'income_evidence', file: new File(['pdf'], 'income.pdf') });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: documentKeys.student('app-1') });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: documentKeys.staff('app-1') });
  });

  it('invalidates both views after a staff review', async () => {
    patch.mockResolvedValue({ data: document });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useReviewDocument(), { wrapper: wrapper(client) });
    result.current.mutate({
      applicationId: 'app-1', documentId: 'doc-1', decision: 'accepted', reason: 'Document has been verified.',
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: documentKeys.student('app-1') });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: documentKeys.staff('app-1') });
  });
});
