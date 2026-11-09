import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ApplicationDocument } from '@/api/types';
import { ApiError } from '@/lib/api';
import { renderWithProviders } from '@/test/render';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const useStudentDocuments = vi.fn();
const useStudentDocumentUpload = vi.fn();
const useStudentDocumentReplacement = vi.fn();
const requestStudentDocumentDownload = vi.fn();

vi.mock('./api', () => ({
  useStudentDocuments: (...args: unknown[]) => useStudentDocuments(...args),
  useStudentDocumentUpload: (...args: unknown[]) => useStudentDocumentUpload(...args),
  useStudentDocumentReplacement: (...args: unknown[]) => useStudentDocumentReplacement(...args),
  requestStudentDocumentDownload: (...args: unknown[]) => requestStudentDocumentDownload(...args),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn() } }));

import { StudentDocumentPanel } from './StudentDocumentPanel';

const baseDocument = (overrides: Partial<ApplicationDocument> = {}): ApplicationDocument => ({
  id: 'doc-1', application_id: 'app-1', original_filename: 'income.pdf', detected_mime_type: 'application/pdf',
  size_bytes: 1024, category: 'income_evidence', status: 'available', scanner_provider: 'scanner',
  scanned_at: '2026-01-01T00:00:00Z', review_status: 'pending', review_reason: null,
  created_at: '2026-01-01T00:00:00Z', reviewed_at: null, replaces_document_id: null,
  ...overrides,
});

const query = (data: ApplicationDocument[] = []) => ({ data, isLoading: false, isError: false, error: null, refetch: vi.fn() });
const mutation = (mutateAsync = vi.fn().mockResolvedValue(baseDocument()), isPending = false) => ({ mutateAsync, isPending });

describe('StudentDocumentPanel', () => {
  beforeEach(() => {
    useStudentDocuments.mockReturnValue(query([baseDocument()]));
    useStudentDocumentUpload.mockReturnValue(mutation());
    useStudentDocumentReplacement.mockReturnValue(mutation());
    requestStudentDocumentDownload.mockReset();
  });

  it('renders document metadata with separate scan and review statuses', () => {
    renderWithProviders(<StudentDocumentPanel applicationId="app-1" isEditable />);
    expect(screen.getByText('income.pdf')).toBeInTheDocument();
    expect(screen.getByText('Available')).toBeInTheDocument();
    expect(screen.getByText('Review: Pending')).toBeInTheDocument();
    expect(screen.getByText('Security checks passed. Staff review is separate.')).toBeInTheDocument();
  });

  it('renders an empty state, loading state, and API error state', () => {
    useStudentDocuments.mockReturnValueOnce(query([]));
    const first = renderWithProviders(<StudentDocumentPanel applicationId="app-1" isEditable />);
    expect(screen.getByText('No supporting documents yet')).toBeInTheDocument();
    first.unmount();

    useStudentDocuments.mockReturnValueOnce({ ...query(), isLoading: true });
    const second = renderWithProviders(<StudentDocumentPanel applicationId="app-1" isEditable />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading documents');
    second.unmount();

    useStudentDocuments.mockReturnValueOnce({ ...query(), isError: true, error: new Error('Unavailable') });
    renderWithProviders(<StudentDocumentPanel applicationId="app-1" isEditable />);
    expect(screen.getByRole('alert')).toHaveTextContent('Unavailable');
  });

  it('validates files before upload and uploads an accepted browser file', async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue(baseDocument());
    useStudentDocumentUpload.mockReturnValue(mutation(mutateAsync));
    renderWithProviders(<StudentDocumentPanel applicationId="app-1" isEditable />);
    await user.click(screen.getByRole('button', { name: 'Upload' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a PDF, JPEG, or PNG document.');

    const file = new File(['pdf'], 'income.pdf', { type: 'application/pdf' });
    await user.upload(screen.getByLabelText('Choose a file'), file);
    await user.click(screen.getByRole('button', { name: 'Upload' }));
    expect(mutateAsync).toHaveBeenCalledWith({ applicationId: 'app-1', category: 'income_evidence', file });
  });

  it('prevents duplicate uploads while the upload mutation is pending', () => {
    useStudentDocumentUpload.mockReturnValue(mutation(vi.fn(), true));
    renderWithProviders(<StudentDocumentPanel applicationId="app-1" isEditable />);
    expect(screen.getByRole('button', { name: /Upload/ })).toBeDisabled();
  });

  it.each(['pending_scan', 'scanning'] as const)('explains that %s documents remain unavailable', (status) => {
    useStudentDocuments.mockReturnValue(query([baseDocument({ status })]));
    renderWithProviders(<StudentDocumentPanel applicationId="app-1" isEditable />);
    expect(screen.getByRole('button', { name: 'Download' })).toBeDisabled();
    expect(screen.getByText('Downloads are available only after security checks pass.')).toBeInTheDocument();
  });

  it('requests a short-lived URL only for available documents', async () => {
    const user = userEvent.setup();
    requestStudentDocumentDownload.mockResolvedValue({ url: 'https://example.test/download', expires_in_seconds: 60 });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    renderWithProviders(<StudentDocumentPanel applicationId="app-1" isEditable />);
    await user.click(screen.getByRole('button', { name: 'Download' }));
    expect(requestStudentDocumentDownload).toHaveBeenCalledWith('doc-1');
    expect(click).toHaveBeenCalled();
    click.mockRestore();
  });

  it('allows a staff-requested replacement and shows a conflict clearly', async () => {
    const user = userEvent.setup();
    const conflict = new ApiError('A replacement document is already awaiting verification.', 409, 'conflict');
    const mutateAsync = vi.fn().mockRejectedValue(conflict);
    useStudentDocuments.mockReturnValue(query([baseDocument({ review_status: 'replacement_requested' })]));
    useStudentDocumentReplacement.mockReturnValue(mutation(mutateAsync));
    renderWithProviders(<StudentDocumentPanel applicationId="app-1" isEditable={false} />);
    await user.click(screen.getByRole('button', { name: 'Replace document' }));
    expect(screen.getByText(/original remains on record/i)).toBeInTheDocument();
    const file = new File(['pdf'], 'replacement.pdf', { type: 'application/pdf' });
    await user.upload(screen.getByLabelText('Replacement file for income.pdf'), file);
    await user.click(screen.getByRole('button', { name: 'Upload replacement' }));
    expect(mutateAsync).toHaveBeenCalledWith({ applicationId: 'app-1', documentId: 'doc-1', category: 'income_evidence', file });
    expect(await screen.findByRole('alert')).toHaveTextContent('A replacement is already awaiting verification. Wait for it to finish');
  });
});
